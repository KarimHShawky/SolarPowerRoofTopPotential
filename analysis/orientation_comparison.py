#!/usr/bin/env python3
"""Compare LoD2 actual roof orientation vs latitude-optimal orientation.

Computes PV, solar thermal (atlite model), and heat pump results for
both orientations using an already-downloaded ERA5 cutout.

Usage:
    python analysis/orientation_comparison.py
    python analysis/orientation_comparison.py --year 2016
    python analysis/orientation_comparison.py --year 2015 --verbose

Requires:
    - An existing ERA5 cutout at data/era5-{year}-leeste.nc
    - Run multi_year_analysis.py first if the cutout doesn't exist yet
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

import xarray as xr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import atlite
import pandas as pd

from src.config import ParametersConfig
from src.data_loading import load_cop, load_demand, load_shape
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
RESOLUTION = 5
ST_PV_POWER_DENSITY = 200


def run_comparison(year: int = 2015) -> dict:
    """Run the orientation comparison and print/save results.

    Parameters
    ----------
    year : int
        ERA5 year to use (cutout must already exist).

    Returns
    -------
    dict
        ``{"actual": {...}, "optimal": {...}}`` with PV/ST/HP totals.
    """
    cutout_path = DATA / f"era5-{year}-leeste.nc"
    if not cutout_path.exists():
        logger.error("Cutout not found: %s", cutout_path)
        logger.error(
            "Download it first with: python analysis/multi_year_analysis.py "
            "--years %d %d", year, year
        )
        sys.exit(1)

    logger.info("Loading cutout for %d …", year)
    cutout = atlite.Cutout(path=str(cutout_path))

    logger.info("Loading static data (buildings, shape) …")
    shape = load_shape(SHAPE_PATH).set_index("Name")
    shape_name = shape.index[0]
    minx, miny, maxx, maxy = shape.total_bounds

    buildings = load_lod2_buildings(LOD2_FILES, crs="25832")
    buildings = buildings.to_crs(3035)
    buildings = clip_buildings_to_region(buildings, shape)

    avg_slope, avg_azimuth = average_roof_params(buildings)
    logger.info("Avg roof slope=%.1f° azimuth=%.1f°", avg_slope, avg_azimuth)

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        temp_raster = tmp.name
    try:
        rasterize_buildings(
            buildings, (minx, miny, maxx, maxy), RESOLUTION, temp_raster
        )

        excluder = atlite.ExclusionContainer(crs=3035, res=RESOLUTION)
        excluder.add_raster(temp_raster, codes=1, invert=True)

        A = cutout.availabilitymatrix(shape, excluder)
        area = cutout.grid.set_index(["y", "x"]).to_crs(3035).area / 1e6
        area = xr.DataArray(area, dims=("spatial",))
        capacity_matrix = A.stack(spatial=["y", "x"]) * area * CAP_PER_SQKM

        load_dhw, load_sph = load_demand(DEMAND_PATH, year=year)
        cop_hp = load_cop(COP_PATH, year=year)

        st_params = ParametersConfig(year=year, capacity_density=CAP_PER_SQKM)

        orientations = {
            "actual": dict(slope=avg_slope, azimuth=avg_azimuth),
            "optimal": "latitude_optimal",
        }

        results = {}
        for label, orient in orientations.items():
            logger.info("Computing PV and ST for %s orientation …", label)

            pv = (
                cutout.pv(
                    panel=atlite.solarpanels.CdTe,
                    orientation=orient,
                    matrix=capacity_matrix,
                    index=shape.index,
                )
                .to_pandas()[shape_name]
            )

            st = compute_solar_thermal(
                cutout, shape, capacity_matrix,
                params=st_params,
                orientation=orient,
            )

            hp = pv * cop_hp

            results[label] = {
                "st_total_mwh": float(st.sum()),
                "pv_total_mwh": float(pv.sum()),
                "hp_total_mwh": float(hp.sum()),
                "st_coverage_pct": float(st.sum() / load_dhw.sum() * 100),
                "pv_coverage_pct": float(pv.sum() / load_sph.sum() * 100),
                "hp_coverage_pct": float(hp.sum() / load_sph.sum() * 100),
            }

        actual = results["actual"]
        optimal = results["optimal"]

        capacity_mw = float(capacity_matrix.sum())
        panel_m2 = float(capacity_matrix.sum() / (ST_PV_POWER_DENSITY * 1e-6))
        ratio_pct = actual["pv_total_mwh"] / optimal["pv_total_mwh"] * 100

        print()
        print("=" * 72)
        print(f"  Orientation Comparison — Leeste LoD2 ({year})")
        print("=" * 72)
        print(f"  Actual roof:     slope={avg_slope:.1f}°, "
              f"azimuth={avg_azimuth:.1f}°")
        print(f"  Latitude-optimal: slope≈53°, azimuth=180° (south-facing)")
        print(f"  Capacity:        {capacity_mw:.2f} MW")
        print(f"  Panel area:      {panel_m2:.0f} m²")
        print(f"  PV ratio:        {ratio_pct:.1f}% (actual / optimal)")
        print("=" * 72)
        print(f"  {'Metric':<30s} {'Actual':>12s} {'Optimal':>12s} "
              f"{'Δ':>10s}")
        print(f"  {'─'*30} {'─'*12} {'─'*12} {'─'*10}")

        metrics = [
            ("PV total [MWh]", "pv_total_mwh", "{:>12.1f}"),
            ("ST total [MWh]", "st_total_mwh", "{:>12.1f}"),
            ("HP total [MWh]", "hp_total_mwh", "{:>12.1f}"),
            ("ST / DHW [%]", "st_coverage_pct", "{:>12.2f}"),
            ("HP / SH [%]", "hp_coverage_pct", "{:>12.2f}"),
        ]

        for name, key, fmt in metrics:
            a = actual[key]
            o = optimal[key]
            if a != 0:
                delta_pct = (o / a - 1) * 100
                delta_str = f"+{delta_pct:.0f}%" if delta_pct > 0 else f"{delta_pct:.0f}%"
            else:
                delta_str = "  N/A"
            print(f"  {name:<30s} {fmt.format(a)} {fmt.format(o)} "
                  f"{delta_str:>10s}")

        print("=" * 72)
        print()

        df = pd.DataFrame({
            "metric": [
                "st_total_mwh", "pv_total_mwh", "hp_total_mwh",
                "st_coverage_pct", "pv_coverage_pct", "hp_coverage_pct",
                "orientation_ratio_pct",
            ],
            "actual": [
                actual["st_total_mwh"], actual["pv_total_mwh"],
                actual["hp_total_mwh"],
                actual["st_coverage_pct"], actual["pv_coverage_pct"],
                actual["hp_coverage_pct"],
                ratio_pct,
            ],
            "optimal": [
                optimal["st_total_mwh"], optimal["pv_total_mwh"],
                optimal["hp_total_mwh"],
                optimal["st_coverage_pct"], optimal["pv_coverage_pct"],
                optimal["hp_coverage_pct"],
                100.0,
            ],
        })
        out_path = RESULTS / "orientation_comparison.csv"
        df.to_csv(out_path, index=False)
        logger.info("Saved orientation comparison → %s", out_path)

    finally:
        Path(temp_raster).unlink(missing_ok=True)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Compare LoD2 actual vs latitude-optimal orientation"
    )
    parser.add_argument(
        "--year", type=int, default=2015,
        help="ERA5 year (must have data/era5-{year}-leeste.nc already)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    run_comparison(year=args.year)


if __name__ == "__main__":
    main()
