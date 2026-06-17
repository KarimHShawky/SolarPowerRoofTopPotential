import pandas as pd
import geopandas as gpd
import atlite

DATA_DIR = "../data"


def load_shape(path):
    """Load a GeoPackage shapefile and reproject to EPSG:3035.

    Parameters
    ----------
    path : str
        Path to the .gpkg file.

    Returns
    -------
    GeoDataFrame
        Region boundary in EPSG:3035.
    """
    return gpd.read_file(path).to_crs(3035)


def load_nuts(path):
    """Load the NUTS regions GeoJSON and reproject to EPSG:3035.

    Used only by the raster approach to define a wide ERA5 cutout extent.

    Parameters
    ----------
    path : str
        Path to the NUTS GeoJSON file.

    Returns
    -------
    GeoDataFrame
        NUTS regions in EPSG:3035.
    """
    return gpd.read_file(path).to_crs(3035)


def load_demand(path, year=2014):
    """Load hourly heat demand CSV, convert timestamps, return series in MW.

    The CSV uses Unix-epoch offsets relative to *year*. The last 4 rows
    (partial data) are dropped and values are converted from kW to MW.

    Parameters
    ----------
    path : str
        Path to the demand CSV.
    year : int
        Reference year for timestamp conversion (default 2014).

    Returns
    -------
    dhw : pd.Series
        Domestic hot water demand in MW.
    sph : pd.Series
        Space heating demand in MW.
    """
    load = pd.read_csv(path)
    seconds_offset = (year - 1970) * 365.25 * 24 * 3600
    load.iloc[:, 0] = pd.to_datetime(load.iloc[:, 0] + seconds_offset, unit="s")
    load = load.drop(load.tail(4).index)
    load = load.set_index(load.columns[0])
    load = load.apply(pd.to_numeric, errors="coerce")
    dhw = load["ABS III_Q_flow_dhw/kW"].copy()
    sph = load["ABS III_Q_flow_sph/kW"].copy()
    dhw[:] /= 1000
    sph[:] /= 1000
    return dhw, sph


def load_cop(path, year=2014):
    """Load COP values from Excel, convert timestamps, return WP_L series.

    Parameters
    ----------
    path : str
        Path to the COP Excel file.
    year : int
        Reference year for timestamp conversion (default 2014).

    Returns
    -------
    pd.Series
        Hourly COP values (WP_L column) with datetime index.
    """
    cop = pd.read_excel(path)
    hours_offset = (year - 1970) * 365.25 * 24
    cop.iloc[:, 0] = pd.to_datetime(cop.iloc[:, 0] + hours_offset, unit="h")
    cop = cop.set_index(cop.columns[0])
    cop.drop(cop.tail(2).index, inplace=True)
    return cop["WP_L"]


def load_cutout(path, x_slice, y_slice, year=2014):
    """Load or create an atlite Cutout for ERA5 weather data.

    If the cutout file already exists, the module/x/y/time/weather
    arguments are ignored (atlite prints a warning, which is harmless).

    Parameters
    ----------
    path : str
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
        path=path,
        module="era5",
        x=x_slice,
        y=y_slice,
        time=str(year),
        weather=True,
    )
