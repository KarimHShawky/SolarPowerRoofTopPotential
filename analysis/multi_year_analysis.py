#!/usr/bin/env python3
"""Multi-year ERA5 analysis for Leeste LoD2 benchmark.

Downloads ERA5 cutouts for each year (if missing), runs the full
PV + solar thermal + heat pump pipeline, and saves annual results
as CSVs in analysis/results/.

Usage:
    python analysis/multi_year_analysis.py
    python analysis/multi_year_analysis.py --years 2015 2024
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import traceback
from pathlib import Path

import atlite
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ParametersConfig
from src.data_loading import load_cop, load_cutout, load_demand, load_shape
from src.lod2_processing import (
    average_roof_params,
    clip_buildings_to_region,
    load_lod2_buildings,
    rasterize_buildings,
)
from src.solar_thermal import compute_solar_thermal

logger = logging.getLogger(__name__)

DATA = ROOT / "data"
RESULTS = HERE / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

SHAPE_PATH = DATA / "leeste3035.gpkg"
DEMAND_PATH = DATA / "Last_240222.csv"
COP_PATH = DATA / "COP_WP.xlsx"
LOD2_FILES = [DATA / "lod2_1.gpkg", DATA / "lod2_2.gpkg", DATA / "lod2_3.gpkg"]

CAP_PER_SQKM = 19
BUFFER = 0.005
RESOLUTION = 5


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def load_static_data():
    shape = load_shape(SHAPE_PATH).set_index("Name")
    shape_name = shape.index[0]
    minx, miny, maxx, maxy = shape.total_bounds

    buildings = load_lod2_buildings(LOD2_FILES, crs="25832")
    buildings = buildings.to_crs(3035)
    buildings = clip_buildings_to_region(buildings, shape)
    logger.info(
        "Loaded %d buildings, total roof area %.0f m²",
        len(buildings),
        buildings["Dachflaeche"].sum(),
    )

    avg_slope, avg_azimuth = average_roof_params(buildings)
    logger.info("Avg roof slope=%.1f° azimuth=%.1f°", avg_slope, avg_azimuth)

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        temp_raster = tmp.name
    rasterize_buildings(buildings, (minx, miny, maxx, maxy), RESOLUTION, temp_raster)

    excluder = atlite.ExclusionContainer(crs=3035, res=RESOLUTION)
    excluder.add_raster(temp_raster, codes=1, invert=True)

    return shape, shape_name, excluder, avg_slope, avg_azimuth, temp_raster


import json
import time

FEATURES = ["height", "runoff", "wind", "temperature", "influx"]
FEATURE_DELAY = 30  # seconds between feature requests
RETRY_403_DELAY = 1800  # 30 min backoff on 403
MAX_403_RETRIES = 3

# Features with 4+ ERA5 variables exceed CDS per-request cost limits.
# Split them monthly to keep each request small enough.
MONTHLY_FEATURES = {"wind", "influx", "temperature"}


def _existing_features(path: Path) -> set:
    """Return set of atlite feature names already present in a cutout.

    Reads the ``feature`` attribute from each data variable rather than
    matching variable names, because atlite stores multiple variables per
    feature (e.g. ``wnd100m``, ``roughness`` → feature ``wind``).
    """
    try:
        ds = xr.open_dataset(path)
        feats = set()
        for da in ds.data_vars.values():
            f = da.attrs.get("feature")
            if f:
                feats.add(f)
        ds.close()
        return feats
    except Exception:
        return set()


def _is_403_error(e: Exception) -> bool:
    msg = str(e)
    return "403" in msg or "Forbidden" in msg


def _prepare_feature(cutout: atlite.Cutout, feat: str, year: int) -> None:
    """Prepare a single feature, retrying with monthly_requests on 403 for large features."""
    monthly = feat in MONTHLY_FEATURES

    if monthly:
        logger.info("Using monthly_requests=True for feature %s (large request)", feat)

    for attempt in range(1, MAX_403_RETRIES + 1):
        try:
            cutout.prepare(
                features=[feat],
                show_progress=True,
                monthly_requests=monthly,
                data_format="netcdf",
            )
            return
        except Exception as e:
            if _is_403_error(e) and attempt < MAX_403_RETRIES:
                logger.warning(
                    "403 on feature %s for %d (attempt %d/%d). "
                    "Backing off %d s …",
                    feat, year, attempt, MAX_403_RETRIES, RETRY_403_DELAY,
                )
                if not monthly and feat in MONTHLY_FEATURES:
                    logger.info(
                        "Retrying %s with monthly_requests=True …", feat
                    )
                    monthly = True
                time.sleep(RETRY_403_DELAY)
            else:
                raise


def ensure_cutout(year: int, shape) -> atlite.Cutout:
    cutout_path = DATA / f"era5-{year}-leeste.nc"
    existing = _existing_features(cutout_path)

    if existing == set(FEATURES):
        logger.info("Loading cached cutout for %d", year)
        return atlite.Cutout(path=str(cutout_path))

    missing = [f for f in FEATURES if f not in existing]
    logger.info(
        "Cutout for %d: %d/%d features done. Missing: %s",
        year, len(existing), len(FEATURES), missing,
    )

    # Load existing file if partial, or create new
    if cutout_path.exists():
        cutout = atlite.Cutout(path=str(cutout_path))
    else:
        x_slice = slice(8.5, 9.0)
        y_slice = slice(51.0, 53.0)
        cutout = load_cutout(cutout_path, x_slice, y_slice, year=year)

    for feat in missing:
        logger.info("Preparing feature %s for %d …", feat, year)
        _prepare_feature(cutout, feat, year)
        time.sleep(FEATURE_DELAY)

    return cutout


def compute_annual_results(year: int, shape, shape_name: str, excluder, orientation: dict) -> dict:
    cutout = ensure_cutout(year, shape)

    load_dhw, load_sph = load_demand(DEMAND_PATH, year=year)
    cop = load_cop(COP_PATH, year=year)

    A = cutout.availabilitymatrix(shape, excluder)
    area = cutout.grid.set_index(["y", "x"]).to_crs(3035).area / 1e6
    area = xr.DataArray(area, dims=("spatial",))
    capacity_matrix = A.stack(spatial=["y", "x"]) * area * CAP_PER_SQKM

    st_params = ParametersConfig(year=year, capacity_density=CAP_PER_SQKM)
    st_potential = compute_solar_thermal(
        cutout, shape, capacity_matrix,
        params=st_params,
        orientation=orientation,
    )

    pv = (
        cutout.pv(
            panel=atlite.solarpanels.CdTe,
            orientation=orientation,
            matrix=capacity_matrix,
            index=shape.index,
        )
        .to_pandas()[shape_name]
    )

    pv_optimal = (
        cutout.pv(
            panel=atlite.solarpanels.CdTe,
            orientation="latitude_optimal",
            matrix=capacity_matrix,
            index=shape.index,
        )
        .to_pandas()[shape_name]
    )

    hp = pv * cop

    return {
        "year": year,
        "st_total_mwh": float(st_potential.sum()),
        "pv_total_mwh": float(pv.sum()),
        "pv_optimal_total_mwh": float(pv_optimal.sum()),
        "hp_total_mwh": float(hp.sum()),
        "dhw_total_mwh": float(load_dhw.sum()),
        "sph_total_mwh": float(load_sph.sum()),
        "st_coverage_pct": float(st_potential.sum() / load_dhw.sum() * 100),
        "pv_coverage_pct": float(pv.sum() / load_sph.sum() * 100),
        "hp_coverage_pct": float(hp.sum() / load_sph.sum() * 100),
        "orientation_ratio_pct": float(pv.sum() / pv_optimal.sum() * 100),
        "st_peak_mw": float(st_potential.max()),
        "pv_peak_mw": float(pv.max()),
        "avg_cop": float(cop.mean()),
        "capacity_mw": float(capacity_matrix.sum()),
        "panel_area_m2": float(capacity_matrix.sum() / (200 * 1e-6)),
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-year ERA5 analysis for Leeste")
    parser.add_argument("--years", nargs=2, type=int, default=[2015, 2024],
                        help="Start and end year (inclusive)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    year_start, year_end = args.years
    years = list(range(year_start, year_end + 1))
    logger.info("Multi-year analysis: %d years (%d–%d)", len(years), year_start, year_end)

    logger.info("Loading static data (buildings, shape, excluder) …")
    shape, shape_name, excluder, avg_slope, avg_azimuth, temp_raster = load_static_data()
    orientation = dict(slope=avg_slope, azimuth=avg_azimuth)

    consecutive_403 = 0
    all_results = []
    for year in years:
        logger.info("─" * 50)
        logger.info("Processing year %d …", year)
        if year > years[0]:
            time.sleep(60)  # longer delay between years
        try:
            result = compute_annual_results(year, shape, shape_name, excluder, orientation)
            all_results.append(result)
            consecutive_403 = 0  # reset on success
            logger.info(
                "Year %d: ST=%.1f%%  PV=%.1f%%  HP=%.1f%%  (of demand)",
                year,
                result["st_coverage_pct"],
                result["pv_coverage_pct"],
                result["hp_coverage_pct"],
            )
            pd.DataFrame(all_results).to_csv(
                RESULTS / "annual_summary_partial.csv", index=False
            )
        except Exception as e:
            logger.error("Year %d failed: %s", year, e)
            traceback.print_exc()
            if _is_403_error(e):
                consecutive_403 += 1
                if consecutive_403 >= 2:
                    logger.warning(
                        "Two consecutive 403s — likely CDS quota exhausted. "
                        "Skipping remaining years. Re-run tomorrow."
                    )
                    break
            continue

    if not all_results:
        logger.error("No results collected — nothing to save.")
        Path(temp_raster).unlink(missing_ok=True)
        return

    df = pd.DataFrame(all_results)
    summary_path = RESULTS / "annual_summary.csv"
    df.to_csv(summary_path, index=False)
    logger.info("Saved annual summary → %s", summary_path)

    for col in ["st_coverage_pct", "pv_coverage_pct", "hp_coverage_pct",
                 "st_total_mwh", "pv_total_mwh", "hp_total_mwh"]:
        vals = df[col]
        logger.info(
            "%s: mean=%.2f  std=%.2f  min=%.2f  max=%.2f",
            col, vals.mean(), vals.std(), vals.min(), vals.max(),
        )

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    colors = ["tab:orange", "tab:blue", "tab:green"]
    labels = ["ST coverage [% DHW]", "PV coverage [% SH]", "HP coverage [% SH]"]
    cols = ["st_coverage_pct", "pv_coverage_pct", "hp_coverage_pct"]

    for ax, col, color, label in zip(axes, cols, colors, labels):
        ax.bar(df["year"], df[col], color=color)
        ax.set_ylabel(label)
        ax.axhline(df[col].mean(), color="gray", ls="--",
                   label=f"mean={df[col].mean():.1f}%")
        ax.legend()
        ax.grid(axis="y")

    axes[-1].set_xlabel("Year")
    fig.suptitle(f"Leeste — Inter-annual Variability ({year_start}–{year_end})")
    fig.tight_layout()
    plot_path = RESULTS / "inter_annual_variability.png"
    fig.savefig(plot_path, dpi=150)
    logger.info("Saved plot → %s", plot_path)

    Path(temp_raster).unlink(missing_ok=True)
    logger.info("Done.")


if __name__ == "__main__":
    main()
