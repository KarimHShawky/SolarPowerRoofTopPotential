import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio as rio

logger = logging.getLogger(__name__)


def load_lod2_buildings(file_paths, crs="25832"):
    """Load and concatenate multiple LoD2 building GeoPackage tiles.

    Parameters
    ----------
    file_paths : list of str or Path
        Paths to the LoD2 .gpkg tile files.
    crs : str
        Original CRS of the building data (default EPSG:25832).

    Returns
    -------
    GeoDataFrame
        All building footprints concatenated, original CRS.
    """
    frames = []
    for p in file_paths:
        p = Path(p)
        if not p.exists():
            raise FileNotFoundError(f"LoD2 tile not found: {p}")
        try:
            frames.append(gpd.read_file(p))
        except Exception as e:
            raise RuntimeError(f"Failed to read LoD2 tile {p}: {e}")

    if not frames:
        raise ValueError("No LoD2 tiles loaded — file_paths is empty")

    buildings = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=crs)
    return buildings


def clip_buildings_to_region(buildings, region):
    """Clip building footprints to the region boundary and parse roof attributes.

    Roof attributes (Dachneigung, Dachorientierung, Dachflaeche) are stored as
    JSON strings in the LoD2 data. This function converts them to numeric values
    by extracting the first element from each list.

    Parameters
    ----------
    buildings : GeoDataFrame
        Building footprints in region CRS.
    region : GeoDataFrame
        Region boundary in the same CRS.

    Returns
    -------
    GeoDataFrame
        Clipped buildings with numeric roof attributes.
    """
    if buildings.empty:
        raise ValueError("Buildings GeoDataFrame is empty")
    if region.empty:
        raise ValueError("Region GeoDataFrame is empty")

    buildings = gpd.overlay(buildings, region, how="intersection")

    if buildings.empty:
        logger.warning("No buildings remain after clipping to region")

    roof_cols = ["Dachneigung", "Dachorientierung", "Dachflaeche"]
    present_cols = [c for c in roof_cols if c in buildings.columns]
    missing = [c for c in roof_cols if c not in buildings.columns]
    if missing:
        logger.warning(
            "Expected roof attribute columns not found: %s. "
            "Available columns: %s",
            missing,
            list(buildings.columns),
        )

    for col in present_cols:
        buildings[col] = buildings[col].apply(
            lambda x: json.loads(x) if isinstance(x, str) else x
        )
        buildings[col] = buildings[col].apply(
            lambda x: x[0] if isinstance(x, list) and len(x) > 0 else None
        )

    return buildings


def rasterize_buildings(buildings, bounds, resolution, output_path):
    """Rasterize building footprints to a GeoTIFF file.

    Parameters
    ----------
    buildings : GeoDataFrame
        Clipped building footprints (CRS must match bounds).
    bounds : tuple
        (minx, miny, maxx, maxy) in the same CRS.
    resolution : float
        Pixel resolution in CRS units (metres).
    output_path : str or Path
        Path for the output GeoTIFF.

    Returns
    -------
    tuple
        (raster_array, transform) where raster has 1 for building pixels.
    """
    if buildings.empty:
        raise ValueError("No buildings to rasterize — GeoDataFrame is empty")

    minx, miny, maxx, maxy = bounds
    width = int((maxx - minx) / resolution)
    height = int((maxy - miny) / resolution)

    if width <= 0 or height <= 0:
        raise ValueError(
            f"Invalid raster dimensions: width={width}, height={height}. "
            f"Check bounds ({bounds}) and resolution ({resolution})."
        )

    transform = rio.transform.from_bounds(minx, miny, maxx, maxy, width, height)

    rasterized = rio.features.rasterize(
        [(geom, 1) for geom in buildings.geometry],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.uint8,
        crs=buildings.crs,
        transform=transform,
    ) as dst:
        dst.write(rasterized, 1)

    logger.info("Rasterized %d buildings to %s", len(buildings), output_path)
    return rasterized, transform


def average_roof_params(buildings):
    """Compute average roof slope and azimuth from LoD2 attributes.

    Parameters
    ----------
    buildings : GeoDataFrame
        Buildings with numeric 'Dachneigung' and 'Dachorientierung' columns.

    Returns
    -------
    tuple
        (avg_slope, avg_azimuth) in degrees.
    """
    if buildings.empty:
        raise ValueError("Cannot compute roof params — buildings is empty")

    slope_col = "Dachneigung"
    azim_col = "Dachorientierung"

    for col in [slope_col, azim_col]:
        if col not in buildings.columns:
            raise KeyError(
                f"Required column '{col}' not found in buildings data. "
                f"Available columns: {list(buildings.columns)}"
            )

    buildings[slope_col] = pd.to_numeric(buildings[slope_col], errors="coerce")
    buildings[azim_col] = pd.to_numeric(buildings[azim_col], errors="coerce")

    if buildings[slope_col].isna().all():
        raise ValueError(f"All values in '{slope_col}' are NaN after conversion")
    if buildings[azim_col].isna().all():
        raise ValueError(f"All values in '{azim_col}' are NaN after conversion")

    avg_slope = buildings[slope_col].mean()
    avg_azimuth = buildings[azim_col].mean()
    return avg_slope, avg_azimuth
