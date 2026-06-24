import logging
from pathlib import Path

import atlite
import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)


def load_shape(path):
    """Load a GeoPackage shapefile and reproject to EPSG:3035.

    Parameters
    ----------
    path : str or Path
        Path to the .gpkg file.

    Returns
    -------
    GeoDataFrame
        Region boundary in EPSG:3035.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Shapefile not found: {path}")
    return gpd.read_file(path).to_crs(3035)


def load_nuts(path):
    """Load the NUTS regions GeoJSON and reproject to EPSG:3035.

    Used only by the raster approach to define a wide ERA5 cutout extent.

    Parameters
    ----------
    path : str or Path
        Path to the NUTS GeoJSON file.

    Returns
    -------
    GeoDataFrame
        NUTS regions in EPSG:3035.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"NUTS file not found: {path}")
    return gpd.read_file(path).to_crs(3035)


def load_demand(path, year=2014):
    """Load hourly heat demand CSV, convert timestamps, return series in MW.

    The CSV uses sequential hour offsets from the start of *year*.
    The last 4 rows (partial data) are dropped and values are converted
    from kW to MW.

    Parameters
    ----------
    path : str or Path
        Path to the demand CSV.
    year : int
        Reference year for timestamp construction (default 2014).

    Returns
    -------
    dhw : pd.Series
        Domestic hot water demand in MW.
    sph : pd.Series
        Space heating demand in MW.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Demand file not found: {path}")

    try:
        load = pd.read_csv(path)
    except Exception as e:
        raise RuntimeError(f"Failed to read demand CSV {path}: {e}")

    if load.shape[1] < 3:
        raise ValueError(
            f"Expected at least 3 columns in demand CSV, got {load.shape[1]}"
        )

    load = load.drop(load.tail(4).index)
    load.index = pd.date_range(
        start=f"{year}-01-01", periods=len(load), freq="h"
    )
    load = load.drop(columns=[load.columns[0]])
    load = load.apply(pd.to_numeric, errors="coerce")

    expected_cols = ["ABS III_Q_flow_dhw/kW", "ABS III_Q_flow_sph/kW"]
    missing = [c for c in expected_cols if c not in load.columns]
    if missing:
        raise KeyError(
            f"Missing expected columns in demand CSV: {missing}. "
            f"Available columns: {list(load.columns)}"
        )

    dhw = load["ABS III_Q_flow_dhw/kW"].copy()
    sph = load["ABS III_Q_flow_sph/kW"].copy()
    dhw[:] /= 1000
    sph[:] /= 1000
    return dhw, sph


def load_cop(path, year=2014):
    """Load COP values from Excel, convert timestamps, return WP_L series.

    Parameters
    ----------
    path : str or Path
        Path to the COP Excel file.
    year : int
        Reference year for timestamp construction (default 2014).

    Returns
    -------
    pd.Series
        Hourly COP values (WP_L column) with datetime index.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"COP file not found: {path}")

    try:
        cop = pd.read_excel(path)
    except Exception as e:
        raise RuntimeError(f"Failed to read COP Excel {path}: {e}")

    if "WP_L" not in cop.columns:
        raise KeyError(
            f"Expected 'WP_L' column. Available columns: {list(cop.columns)}"
        )

    cop.drop(cop.tail(2).index, inplace=True)
    cop.index = pd.date_range(
        start=f"{year}-01-01", periods=len(cop), freq="h"
    )
    return cop["WP_L"]


def load_cutout(path, x_slice, y_slice, year=2014):
    """Load or create an atlite Cutout for ERA5 weather data.

    If the cutout file already exists, the module/x/y/time/weather
    arguments are ignored (atlite prints a warning, which is harmless).

    Parameters
    ----------
    path : str or Path
        Path to the .nc cutout file.
    x_slice : slice
        Longitude slice for the region.
    y_slice : slice
        Latitude slice for the region.
    year : int
        Year of the cutout (default 2014).

    Returns
    -------
    atlite.Cutout
        Ready-to-use weather cutout.
    """
    return atlite.Cutout(
        path=str(path),
        module="era5",
        x=x_slice,
        y=y_slice,
        time=str(year),
        weather=True,
    )
