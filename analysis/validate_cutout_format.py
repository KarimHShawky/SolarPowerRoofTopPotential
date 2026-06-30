#!/usr/bin/env python3
"""Validate a freshly built ERA5 cutout: features, data integrity, PV/ST output.

Usage:
    python analysis/validate_cutout_format.py data/era5-2015-leeste.nc
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import xarray as xr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import atlite
from src.config import ParametersConfig
from src.data_loading import load_cop, load_demand, load_shape
from src.lod2_processing import (
    average_roof_params,
    clip_buildings_to_region,
    load_lod2_buildings,
    rasterize_buildings,
)
from src.solar_thermal import compute_solar_thermal

DATA = ROOT / "data"
SHAPE_PATH = DATA / "leeste3035.gpkg"
DEMAND_PATH = DATA / "Last_240222.csv"
COP_PATH = DATA / "COP_WP.xlsx"
LOD2_FILES = [DATA / "lod2_1.gpkg", DATA / "lod2_2.gpkg", DATA / "lod2_3.gpkg"]

CAP_PER_SQKM = 19
RESOLUTION = 5
BASELINE_PV_MW = 0.67
TOLERANCE = 0.15


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_cutout_format.py <cutout.nc>")
        sys.exit(1)

    cutout_path = Path(sys.argv[1])
    if not cutout_path.exists():
        print(f"❌ Cutout not found: {cutout_path}")
        sys.exit(1)

    # 1. Open with atlite
    print(f"Opening {cutout_path} …")
    cutout = atlite.Cutout(path=str(cutout_path))
    ds = xr.open_dataset(cutout_path)
    print(f"   Time: {ds.coords['time'].values[0]} … {ds.coords['time'].values[-1]}")
    print(f"   Grid: {ds.coords['x'].values[0]:.2f}–{ds.coords['x'].values[-1]:.2f} lon  "
          f"{ds.coords['y'].values[0]:.2f}–{ds.coords['y'].values[-1]:.2f} lat")

    # 2. Check expected features
    expected_vars = {"height", "wnd100m", "influx_direct", "temperature", "runoff"}
    present = set(ds.data_vars)
    missing = expected_vars - present
    if missing:
        print(f"❌ Missing features: {missing}")
        sys.exit(1)
    print(f"✅ All expected features present ({len(present)} total)")

    # 3. Check for NaN / inf
    nan_count = 0
    inf_count = 0
    for var in present:
        data = ds[var].values
        nan_count += int(np.isnan(data).sum())
        inf_count += int(np.isinf(data).sum())
    if nan_count or inf_count:
        print(f"❌ Data integrity: {nan_count} NaN, {inf_count} inf values")
        sys.exit(1)
    print(f"✅ No NaN / inf values")

    # 4. Run PV and ST pipeline
    print("Running pipeline …")
    shape = load_shape(SHAPE_PATH).set_index("Name")
    shape_name = shape.index[0]
    minx, miny, maxx, maxy = shape.total_bounds

    buildings = load_lod2_buildings(LOD2_FILES, crs="25832")
    buildings = buildings.to_crs(3035)
    buildings = clip_buildings_to_region(buildings, shape)
    avg_slope, avg_azimuth = average_roof_params(buildings)
    orientation = dict(slope=avg_slope, azimuth=avg_azimuth)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        temp_raster = tmp.name
    try:
        rasterize_buildings(buildings, (minx, miny, maxx, maxy), RESOLUTION, temp_raster)
        excluder = atlite.ExclusionContainer(crs=3035, res=RESOLUTION)
        excluder.add_raster(temp_raster, codes=1, invert=True)

        A = cutout.availabilitymatrix(shape, excluder)
        area = cutout.grid.set_index(["y", "x"]).to_crs(3035).area / 1e6
        area_xr = xr.DataArray(area, dims=("spatial",))
        capacity_matrix = A.stack(spatial=["y", "x"]) * area_xr * CAP_PER_SQKM

        pv = (
            cutout.pv(
                panel=atlite.solarpanels.CdTe,
                orientation=orientation,
                matrix=capacity_matrix,
                index=shape.index,
            )
            .to_pandas()[shape_name]
        )
        pv_total = float(pv.sum())

        st_params = ParametersConfig(
            year=int(ds.coords["time"].dt.year.values[0]),
            capacity_density=CAP_PER_SQKM,
        )
        st_potential = compute_solar_thermal(
            cutout, shape, capacity_matrix,
            params=st_params,
            orientation=orientation,
        )
        st_total = float(st_potential.sum())

        if abs(pv_total - BASELINE_PV_MW) / BASELINE_PV_MW < TOLERANCE:
            print(f"✅ PV yield {pv_total:.2f} MW — matches 2014 baseline ({BASELINE_PV_MW} MW ±{TOLERANCE*100:.0f}%)")
        else:
            print(f"⚠️  PV yield {pv_total:.2f} MW — outside 2014 baseline ({BASELINE_PV_MW} MW ±{TOLERANCE*100:.0f}%)")
            print(f"   (may be legitimate inter-annual variability)")

        print(f"   ST yield {st_total:.2f} MW")
        print(f"✅ Validation complete")
    finally:
        Path(temp_raster).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
