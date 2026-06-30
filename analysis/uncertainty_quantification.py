#!/usr/bin/env python3
"""Uncertainty quantification via Monte Carlo simulation.

Pre-computes the atlite solar thermal and PV converters once, then
applies parameter variations analytically. This avoids calling atlite's
expensive ``convert_and_aggregate`` for each MC sample.

Usage:
    python analysis/uncertainty_quantification.py
    python analysis/uncertainty_quantification.py --n 5000 --seed 42
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import traceback
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from scipy.stats import norm, uniform, qmc

import atlite

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

logger = logging.getLogger(__name__)

DATA = ROOT / "data"
RESULTS = HERE / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

SHAPE_PATH = DATA / "leeste3035.gpkg"
DEMAND_PATH = DATA / "Last_240222.csv"
COP_PATH = DATA / "COP_WP.xlsx"
LOD2_FILES = [DATA / "lod2_1.gpkg", DATA / "lod2_2.gpkg", DATA / "lod2_3.gpkg"]
CUTOUT_PATH = DATA / "era5-2015-leeste.nc"

RESOLUTION = 5

# --- Parameter definitions ---

PARAMS = {
    "cap_per_sqkm": {
        "dist": norm, "loc": 19.0, "scale": 2.0,
        "label": "Capacity density [MW/km²]",
    },
    "st_pv_power_density": {
        "dist": norm, "loc": 200.0, "scale": 10.0,
        "label": "Panel power density [W/m²]",
    },
    "st_c0": {
        "dist": uniform, "loc": 0.75, "scale": 0.10,
        "label": "ST c₀ [—]",
    },
    "st_c1": {
        "dist": uniform, "loc": 2.5, "scale": 1.0,
        "label": "ST c₁ [W/m²K]",
    },
    "t_store": {
        "dist": uniform, "loc": 70.0, "scale": 20.0,
        "label": "Storage temp [°C]",
    },
    "cop_multiplier": {
        "dist": norm, "loc": 1.0, "scale": 0.05,
        "label": "COP multiplier [—]",
    },
    "demand_multiplier": {
        "dist": norm, "loc": 1.0, "scale": 0.10,
        "label": "Demand multiplier [—]",
    },
}

PARAM_NAMES = list(PARAMS)
N_PARAMS = len(PARAM_NAMES)


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

    buildings = load_lod2_buildings(LOD2_FILES, crs="25832")
    buildings = buildings.to_crs(3035)
    buildings = clip_buildings_to_region(buildings, shape)
    logger.info("Loaded %d buildings, total roof area %.0f m²",
                len(buildings), buildings["Dachflaeche"].sum())

    avg_slope, avg_azimuth = average_roof_params(buildings)
    logger.info("Avg roof slope=%.1f° azimuth=%.1f°", avg_slope, avg_azimuth)

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        temp_raster = tmp.name
    rasterize_buildings(buildings, (minx := shape.total_bounds[0], shape.total_bounds[1],
                                    shape.total_bounds[2], shape.total_bounds[3]),
                        RESOLUTION, temp_raster)

    return shape, shape_name, avg_slope, avg_azimuth, temp_raster


def _align_index(series, target_index):
    """Reindex to target, filling gaps (handles DST hour mismatches)."""
    return series.reindex(target_index).fillna(0.0)


def precompute_baselines(cutout, shape, shape_name, temp_raster,
                         slope, azimuth) -> dict:
    """Run atlite converters once and extract intermediate data."""
    orientation = dict(slope=slope, azimuth=azimuth)

    excluder = atlite.ExclusionContainer(crs=3035, res=RESOLUTION)
    excluder.add_raster(temp_raster, codes=1, invert=True)
    A = cutout.availabilitymatrix(shape, excluder)
    A_stack = A.stack(spatial=["y", "x"])
    area_km2 = cutout.grid.set_index(["y", "x"]).to_crs(3035).area / 1e6
    area_km2_arr = xr.DataArray(area_km2, dims=("spatial",))
    cap_base = A_stack * area_km2_arr * 19.0  # base cap_per_sqkm = 19
    area_m2_base = cap_base / (200.0 * 1e-6)  # base pv_density = 200
    total_area_m2 = float(area_m2_base.sum())

    # --- PV baseline (once, then scale linearly with capacity) ---
    pv_base = (
        cutout.pv(
            panel=atlite.solarpanels.CdTe,
            orientation=orientation,
            matrix=cap_base,
            index=shape.index,
        )
        .to_pandas()[shape_name]
    )
    pv_opt_base = (
        cutout.pv(
            panel=atlite.solarpanels.CdTe,
            orientation="latitude_optimal",
            matrix=cap_base,
            index=shape.index,
        )
        .to_pandas()[shape_name]
    )

    # --- ST baseline: run once, then recover G_tilted from hours with output ---
    st_cfg = ParametersConfig(
        year=2015, capacity_density=19.0,
        st_c0=0.80, st_c1=3.0, st_t_store=80.0,
    )
    from src.solar_thermal import compute_solar_thermal
    st_base_mw = compute_solar_thermal(
        cutout, shape, cap_base,
        params=st_cfg, orientation=orientation,
    )
    st_per_m2 = st_base_mw * 1e6 / total_area_m2  # W/m² heat

    # Get capacity-weighted average air temperature
    def _get_temp(ds, orientation):
        return ds["temperature"] - 273.15
    norm = cap_base / cap_base.sum()
    temp_w = cutout.convert_and_aggregate(
        convert_func=_get_temp,
        orientation=orientation,
        matrix=norm,
        index=shape.index,
    )
    if isinstance(temp_w, list):
        temp_w = xr.concat(temp_w, dim="time")
    temp_air = _align_index(temp_w.to_pandas()[shape_name], st_base_mw.index)

    # Recover per-m² G_tilted from hours where ST > 0.
    # P_total = c0 * sum(A*G) - c1 * T_store * sum(A) + c1 * sum(A*T)
    # per m²: P/m² = c0*G_avg - c1*(T_store - T_avg)
    # G_avg = (P/m² + c1*(T_store - T_avg)) / c0
    st_per_m2_pos = st_per_m2 > 0
    g_tilted = pd.Series(0.0, index=st_base_mw.index, name="G_tilted")
    g_tilted[st_per_m2_pos] = (
        (st_per_m2[st_per_m2_pos] + 3.0 * (80.0 - temp_air[st_per_m2_pos])) / 0.80
    )
    g_tilted = g_tilted.clip(lower=0)

    # Recover G_tilted only where P_ST > 0 (formula is valid)
    # P = c0*G - c1*(T_store - T_air)  =>  G = (P + c1*(T_store - T_air)) / c0
    g_tilted = pd.Series(0.0, index=st_base_mw.index, name="G_tilted")
    pos = st_per_m2 > 0
    g_tilted[pos] = (
        (st_per_m2[pos] + 3.0 * (80.0 - temp_air[pos])) / 0.80
    )
    g_tilted[g_tilted < 0] = 0.0

    return {
        "shape_name": shape_name,
        "total_area_m2": total_area_m2,
        "cap_base": cap_base,
        "pv_base": pv_base,
        "pv_opt_base": pv_opt_base,
        "g_tilted": g_tilted,
        "temp_air": temp_air,
    }


def sample_parameters(n: int, seed: int = 42) -> pd.DataFrame:
    sampler = qmc.LatinHypercube(d=N_PARAMS, seed=seed)
    samples = sampler.random(n)
    df = pd.DataFrame(index=range(n), columns=PARAM_NAMES)
    for i, name in enumerate(PARAM_NAMES):
        p = PARAMS[name]
        df[name] = p["dist"].ppf(samples[:, i], loc=p["loc"], scale=p["scale"])
    return df


def run_mc(baseline: dict, cop_base, dhw_base, sph_base,
           params: pd.DataFrame) -> pd.DataFrame:
    """Vectorized Monte Carlo using precomputed baselines."""
    target_idx = dhw_base.index

    pv_base = _align_index(baseline["pv_base"], target_idx)
    pv_opt_base = _align_index(baseline["pv_opt_base"], target_idx)
    g_tilted = _align_index(baseline["g_tilted"], target_idx)
    temp_air = _align_index(baseline["temp_air"], target_idx)
    cop_aligned = _align_index(cop_base, target_idx)
    total_area_m2 = baseline["total_area_m2"]

    cap_factor = params["cap_per_sqkm"] / 19.0
    n = len(params)
    results = params.copy()

    base_cap_sum = float(baseline["cap_base"].sum())
    capacity_mw = cap_factor * base_cap_sum
    results["capacity_mw"] = capacity_mw

    panel_area = capacity_mw / (params["st_pv_power_density"] * 1e-6)
    results["panel_area_m2"] = panel_area

    # PV scales linearly with capacity
    pv_mw = pd.DataFrame(
        np.outer(cap_factor.values, pv_base.values),
        index=params.index,
        columns=pv_base.index,
    )
    results["pv_total_mwh"] = pv_mw.sum(axis=1).values
    results["pv_optimal_mwh"] = (cap_factor.values * pv_opt_base.sum()).sum()

    # ST per m²: c0*G - c1*(T_store - T_air)  then clip, scale by area
    st_per_m2 = pd.DataFrame(
        np.outer(params["st_c0"].values, g_tilted.values)
        - np.outer(params["st_c1"].values * params["t_store"].values, np.ones(len(g_tilted)))
        + np.outer(params["st_c1"].values, temp_air.values),
        index=params.index,
        columns=g_tilted.index,
    )
    st_per_m2[st_per_m2 < 0] = 0.0
    st_mw = st_per_m2.multiply(panel_area, axis=0) / 1e6
    results["st_total_mwh"] = st_mw.sum(axis=1).values

    # HP
    hp_mw = pv_mw.multiply(cop_aligned.values * params["cop_multiplier"].values[:, None], axis=1)
    results["hp_total_mwh"] = hp_mw.sum(axis=1).values

    dhw_total = dhw_base.sum() * params["demand_multiplier"]
    sph_total = sph_base.sum() * params["demand_multiplier"]
    results["dhw_mwh"] = dhw_total
    results["sph_mwh"] = sph_total

    results["st_coverage_pct"] = results["st_total_mwh"] / dhw_total * 100
    results["pv_coverage_pct"] = results["pv_total_mwh"] / sph_total * 100
    results["hp_coverage_pct"] = results["hp_total_mwh"] / sph_total * 100

    return results


def main():
    parser = argparse.ArgumentParser(description="Uncertainty quantification")
    parser.add_argument("--n", type=int, default=5000, help="Number of MC samples")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    logger.info("Loading static data …")
    shape, shape_name, avg_slope, avg_azimuth, temp_raster = load_static_data()

    logger.info("Loading 2015 cutout …")
    cutout = atlite.Cutout(path=str(CUTOUT_PATH))

    logger.info("Loading demand & COP …")
    dhw_base, sph_base = load_demand(DEMAND_PATH, year=2015)
    cop_base = load_cop(COP_PATH, year=2015)

    logger.info("Pre-computing atlite baselines (1x PV + 1x ST) …")
    baseline = precompute_baselines(
        cutout, shape, shape_name, temp_raster,
        avg_slope, avg_azimuth,
    )

    logger.info("Generating %d LHS samples …", args.n)
    samples = sample_parameters(args.n, seed=args.seed)

    logger.info("Running vectorized MC …")
    results = run_mc(baseline, cop_base, dhw_base, sph_base, samples)

    outpath = RESULTS / "uq_results.csv"
    results.to_csv(outpath, index=False)
    logger.info("Saved %d results → %s", len(results), outpath)

    # Summary statistics
    logger.info("─" * 50)
    logger.info("Summary statistics (n=%d):", len(results))
    for col in ["st_coverage_pct", "pv_coverage_pct", "hp_coverage_pct",
                "capacity_mw", "st_total_mwh", "pv_total_mwh", "hp_total_mwh"]:
        vals = results[col]
        logger.info(
            "  %s: mean=%.2f  std=%.2f  p5=%.2f  p95=%.2f",
            col, vals.mean(), vals.std(),
            vals.quantile(0.05), vals.quantile(0.95),
        )

    # Tornado sensitivity: correlation of each input with each output
    corr = results[PARAM_NAMES + ["st_coverage_pct", "pv_coverage_pct", "hp_coverage_pct"]].corr()
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5))
    outputs = ["st_coverage_pct", "pv_coverage_pct", "hp_coverage_pct"]
    titles = ["ST coverage [% DHW]", "PV coverage [% SH]", "HP coverage [% SH]"]
    for ax, out, title in zip(axes, outputs, titles):
        corr_vals = corr[out].drop(out, errors="ignore")
        corr_vals = corr_vals[corr_vals.index.isin(PARAM_NAMES)]
        corr_vals = corr_vals.sort_values()
        colors = ["tab:red" if v < 0 else "tab:blue" for v in corr_vals.values]
        ax.barh(range(len(corr_vals)), corr_vals.values, color=colors)
        ax.set_yticks(range(len(corr_vals)))
        ax.set_yticklabels([PARAMS[k]["label"] for k in corr_vals.index], fontsize=7)
        ax.set_xlabel("Pearson correlation")
        ax.set_title(title)
        ax.axvline(0, color="gray", lw=0.5)
    fig.suptitle("Sensitivity — input-output correlations")
    fig.tight_layout()
    plot_path = RESULTS / "uq_sensitivity.png"
    fig.savefig(plot_path, dpi=150)
    logger.info("Saved sensitivity plot → %s", plot_path)

    # Distribution histograms
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))
    for ax, col, title in zip(axes, outputs, titles):
        ax.hist(results[col], bins=50, color="steelblue", edgecolor="white")
        ax.axvline(results[col].mean(), color="red", ls="--",
                   label=f"mean={results[col].mean():.1f}")
        ax.axvline(results[col].quantile(0.05), color="orange", ls=":",
                   label=f"p5={results[col].quantile(0.05):.1f}")
        ax.axvline(results[col].quantile(0.95), color="orange", ls=":",
                   label=f"p95={results[col].quantile(0.95):.1f}")
        ax.set_xlabel(title)
        ax.set_ylabel("Count")
        ax.legend(fontsize=6)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle(f"Uncertainty distributions (n={len(results)}, LHS)")
    fig.tight_layout()
    hist_path = RESULTS / "uq_distributions.png"
    fig.savefig(hist_path, dpi=150)
    logger.info("Saved distribution plot → %s", hist_path)

    Path(temp_raster).unlink(missing_ok=True)
    logger.info("Done.")


if __name__ == "__main__":
    main()
