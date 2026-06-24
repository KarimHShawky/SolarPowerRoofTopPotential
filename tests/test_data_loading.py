from pathlib import Path

import pytest

from src.data_loading import load_cop, load_cutout, load_demand, load_nuts, load_shape

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestLoadShape:
    def test_loads_geopackage(self):
        path = DATA_DIR / "leeste3035.gpkg"
        gdf = load_shape(path)
        assert gdf is not None
        assert str(gdf.crs) == "EPSG:3035"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_shape(DATA_DIR / "nonexistent.gpkg")


class TestLoadNuts:
    def test_loads_geojson(self):
        path = DATA_DIR / "NUTS_RG_10M_2021_4326.geojson"
        gdf = load_nuts(path)
        assert gdf is not None
        assert str(gdf.crs) == "EPSG:3035"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_nuts(DATA_DIR / "nonexistent.geojson")


class TestLoadDemand:
    def test_loads_demand(self):
        path = DATA_DIR / "Last_240222.csv"
        dhw, sph = load_demand(path, year=2014)
        assert dhw is not None
        assert sph is not None
        assert len(dhw) == len(sph)
        assert dhw.name == "ABS III_Q_flow_dhw/kW"
        assert sph.name == "ABS III_Q_flow_sph/kW"

    def test_units_in_mw(self):
        path = DATA_DIR / "Last_240222.csv"
        dhw, _ = load_demand(path, year=2014)
        # Maximum DHW should be reasonable for a district (< 100 MW)
        assert dhw.max() < 100
        assert dhw.min() >= 0

    def test_datetime_index(self):
        path = DATA_DIR / "Last_240222.csv"
        dhw, _ = load_demand(path, year=2014)
        assert dhw.index[0].year == 2014
        assert dhw.index[0].month == 1
        assert dhw.index[0].day == 1

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_demand(DATA_DIR / "nonexistent.csv")

    def test_bad_column_csv(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text("a,b\n1,2\n3,4\n5,6\n")
        with pytest.raises((KeyError, ValueError)):
            load_demand(bad, year=2014)

    def test_years_differ(self):
        path = DATA_DIR / "Last_240222.csv"
        dhw_2014, _ = load_demand(path, year=2014)
        dhw_2015, _ = load_demand(path, year=2015)
        assert dhw_2014.index[0].year == 2014
        assert dhw_2015.index[0].year == 2015
        assert len(dhw_2014) == len(dhw_2015)


class TestLoadCop:
    def test_loads_cop(self):
        path = DATA_DIR / "COP_WP.xlsx"
        cop = load_cop(path, year=2014)
        assert cop is not None
        assert cop.name == "WP_L"

    def test_values_reasonable(self):
        path = DATA_DIR / "COP_WP.xlsx"
        cop = load_cop(path, year=2014)
        # COP values should be within plausible range for air-source heat pumps
        assert cop.min() > 0.5
        assert cop.max() <= 10.0
        assert cop.mean() > 2.0

    def test_datetime_index(self):
        path = DATA_DIR / "COP_WP.xlsx"
        cop = load_cop(path, year=2014)
        assert cop.index[0].year == 2014
        assert cop.index[0].month == 1
        assert cop.index[0].day == 1

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_cop(DATA_DIR / "nonexistent.xlsx")

    def test_missing_column(self, tmp_path):
        bad = tmp_path / "bad.xlsx"
        import pandas as pd
        pd.DataFrame({"A": [1, 2, 3]}).to_excel(bad, index=False)
        with pytest.raises(KeyError):
            load_cop(bad, year=2014)


class TestLoadCutout:
    def test_returns_cutout_object(self, tmp_path):
        nc_path = tmp_path / "test_cutout.nc"
        cutout = load_cutout(nc_path, slice(8, 9), slice(52, 53), year=2014)
        assert cutout is not None
        assert str(cutout.path) == str(nc_path)
