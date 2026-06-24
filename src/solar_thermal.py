from __future__ import annotations

import logging

import xarray as xr

logger = logging.getLogger(__name__)


def compute_solar_thermal(
    cutout, shape, capacity_matrix, params, orientation="latitude_optimal",
):
    """Compute solar thermal collector potential using the configured model.

    Parameters
    ----------
    cutout : atlite.Cutout
        ERA5 weather cutout.
    shape : GeoDataFrame
        Region boundary (must have a ``.index`` attribute).
    capacity_matrix : xr.DataArray
        Installed capacity per grid cell (MW).
    params : ParametersConfig
        Configuration with ``st_model`` and collector parameters.
    orientation : str or dict, optional
        ``"latitude_optimal"`` (default) or ``dict(slope=..., azimuth=...)``.

    Returns
    -------
    pd.Series
        Hourly solar thermal heat output (MW) with a datetime index.
    """
    if params.st_model == "atlite":
        return _atlite_solar_thermal(
            cutout, shape, capacity_matrix, params, orientation,
        )
    if params.st_model == "oemof":
        return _oemof_solar_thermal(
            cutout, shape, capacity_matrix, params, orientation,
        )
    raise ValueError(
        f"Unknown st_model={params.st_model!r}. Choose 'atlite' or 'oemof'."
    )


# ---------------------------------------------------------------------------
# Model A — atlite built-in  (Henning & Palzer 2014, linear efficiency)
# ---------------------------------------------------------------------------

def _atlite_solar_thermal(cutout, shape, capacity_matrix, params, orientation):
    """Use :meth:`atlite.Cutout.solar_thermal` with a linear efficiency model.

    Efficiency:  η = c0 − c1 × (T_store − T_amb) / G_tilted

    Note: ``cutout.solar_thermal()`` returns **W/m²**, so the matrix must
    be collector **area** (m²), not capacity (MW).  We recover the area
    from the capacity matrix via ``capacity_density``.
    """
    area_m2 = capacity_matrix / (params.st_pv_power_density * 1e-6)

    st = cutout.solar_thermal(
        orientation=orientation,
        c0=params.st_c0,
        c1=params.st_c1,
        t_store=params.st_t_store,
        matrix=area_m2,
        index=shape.index,
    )
    if isinstance(st, list):
        st = xr.concat(st, dim="time")
    if "Name" in st.dims:
        st = st.sum(dim="Name")
    return (st / 1e6).to_pandas()


# ---------------------------------------------------------------------------
# Model B — EN 12975 quadratic efficiency  (oemof-thermal compatible)
# ---------------------------------------------------------------------------

def _oemof_solar_thermal(cutout, shape, capacity_matrix, params, orientation):
    """Flat-plate collector with the EN 12975 quadratic efficiency model.

    This is the same model used by ``oemof.thermal.solar_thermal_collector``:

        η = η₀ − a₁ × ΔT/G − a₂ × ΔT²/G

    where  ΔT = T_inlet + ΔT_n − T_amb.

    The calculation runs inside :meth:`atlite.Cutout.convert_and_aggregate` so
    that spatial aggregation via `capacity_matrix` works identically to the
    built-in ``cutout.solar_thermal()`` and ``cutout.pv()`` methods.
    """
    from atlite.pv.irradiation import TiltedIrradiation
    from atlite.pv.orientation import SurfaceOrientation, get_orientation
    from atlite.pv.solar_position import SolarPosition

    def _convert_oemof(ds, orientation, eta_0, a_1, a_2, temp_inlet, delta_temp_n):
        if not callable(orientation):
            orientation = get_orientation(orientation)
        solar_position = SolarPosition(ds)
        surface_orientation = SurfaceOrientation(ds, solar_position, orientation)
        irradiation = TiltedIrradiation(
            ds, solar_position, surface_orientation, "simple", "simple",
        )

        temp_amb_celsius = ds["temperature"] - 273.15
        delta_t = temp_inlet + delta_temp_n - temp_amb_celsius
        safe = irradiation.where(irradiation != 0)
        eta = eta_0 - a_1 * (delta_t / safe).fillna(0) - a_2 * (
            delta_t ** 2 / safe
        ).fillna(0)

        output = irradiation * eta
        return output.where(output > 0, 0.0)

    area_m2 = capacity_matrix / (params.st_pv_power_density * 1e-6)

    st = cutout.convert_and_aggregate(
        convert_func=_convert_oemof,
        orientation=orientation,
        eta_0=params.st_eta_0,
        a_1=params.st_a_1,
        a_2=params.st_a_2,
        temp_inlet=params.st_temp_inlet,
        delta_temp_n=params.st_delta_temp_n,
        matrix=area_m2,
        index=shape.index,
    )
    if isinstance(st, list):
        st = xr.concat(st, dim="time")
    if "Name" in st.dims:
        st = st.sum(dim="Name")
    return (st / 1e6).to_pandas()
