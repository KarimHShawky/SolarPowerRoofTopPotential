from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio as rio

logger = logging.getLogger(__name__)


def download_osm_buildings(place_name, cache_path=None):
    """Download OSM building footprints for a place name.

    Parameters
    ----------
    place_name : str
        Place name query (e.g. ``"Leeste, Weyhe, Germany"``).
    cache_path : str or Path, optional
        If given, save the GeoDataFrame to this GeoPackage for reuse.

    Returns
    -------
    GeoDataFrame
        Building footprints in EPSG:4326.
    """
    try:
        import osmnx as ox
    except ImportError:
        raise ImportError(
            "osmnx is required to download OSM building data. "
            "Install with: pip install osmnx"
        )

    logger.info("Downloading OSM buildings for '%s' ...", place_name)
    buildings = ox.features_from_place(place_name, tags={"building": True})

    mask = buildings.geometry.type.isin(["Polygon", "MultiPolygon"])
    buildings = buildings[mask]
    logger.info("Downloaded %d building features", len(buildings))

    if cache_path:
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        dump = buildings.to_crs("EPSG:4326")
        dump.to_file(cache_path, driver="GPKG")
        logger.info("Cached OSM buildings to %s", cache_path)

    return buildings


def clip_to_region(buildings, region):
    """Clip building footprints to the region boundary.

    Parameters
    ----------
    buildings : GeoDataFrame
        OSM building footprints in region CRS.
    region : GeoDataFrame
        Region boundary in the same CRS.

    Returns
    -------
    GeoDataFrame
        Clipped buildings.
    """
    if buildings.empty:
        raise ValueError("Buildings GeoDataFrame is empty")
    if region.empty:
        raise ValueError("Region GeoDataFrame is empty")

    buildings = gpd.overlay(buildings, region, how="intersection")

    if buildings.empty:
        logger.warning("No buildings remain after clipping to region")

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


def compute_footprint_area(buildings):
    """Compute total building footprint area.

    Parameters
    ----------
    buildings : GeoDataFrame
        Building footprints in a projected CRS.

    Returns
    -------
    float
        Total footprint area in m².
    """
    if buildings.empty:
        return 0.0
    return buildings.geometry.area.sum()
