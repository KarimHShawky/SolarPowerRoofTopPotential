import json
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio as rio


def load_lod2_buildings(file_paths, crs="25832"):
    """Load and concatenate multiple LoD2 building GeoPackage tiles.

    Parameters
    ----------
    file_paths : list of str
        Paths to the LoD2 .gpkg tile files.
    crs : str
        Original CRS of the building data (default EPSG:25832).

    Returns
    -------
    GeoDataFrame
        All building footprints concatenated, original CRS.
    """
    frames = [gpd.read_file(p) for p in file_paths]
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
    buildings = gpd.overlay(buildings, region, how="intersection")

    for col in ["Dachneigung", "Dachorientierung", "Dachflaeche"]:
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
    output_path : str
        Path for the output GeoTIFF.

    Returns
    -------
    tuple
        (raster_array, transform) where raster has 1 for building pixels.
    """
    minx, miny, maxx, maxy = bounds
    width = int((maxx - minx) / resolution)
    height = int((maxy - miny) / resolution)
    transform = rio.transform.from_bounds(minx, miny, maxx, maxy, width, height)

    rasterized = rio.features.rasterize(
        [(geom, 1) for geom in buildings.geometry],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    )

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
    buildings["Dachneigung"] = pd.to_numeric(buildings["Dachneigung"], errors="coerce")
    buildings["Dachorientierung"] = pd.to_numeric(
        buildings["Dachorientierung"], errors="coerce"
    )
    avg_slope = buildings["Dachneigung"].mean()
    avg_azimuth = buildings["Dachorientierung"].mean()
    return avg_slope, avg_azimuth
