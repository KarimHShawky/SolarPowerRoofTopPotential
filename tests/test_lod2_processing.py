from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from src.lod2_processing import (
    average_roof_params,
    clip_buildings_to_region,
    load_lod2_buildings,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestLoadLod2Buildings:
    def test_loads_tiles(self):
        paths = [
            DATA_DIR / "lod2_1.gpkg",
            DATA_DIR / "lod2_2.gpkg",
            DATA_DIR / "lod2_3.gpkg",
        ]
        buildings = load_lod2_buildings(paths)
        assert buildings is not None
        assert len(buildings) > 0
        assert "geometry" in buildings.columns

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_lod2_buildings([DATA_DIR / "nonexistent.gpkg"])

    def test_empty_list(self):
        with pytest.raises(ValueError, match="empty"):
            load_lod2_buildings([])

    def test_single_tile(self):
        path = DATA_DIR / "lod2_1.gpkg"
        buildings = load_lod2_buildings([path])
        assert len(buildings) > 0


class TestClipBuildingsToRegion:
    @pytest.fixture
    def buildings(self):
        return gpd.GeoDataFrame(
            {
                "geometry": [
                    Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
                    Polygon([(5, 5), (5, 6), (6, 6), (6, 5)]),
                ],
                "Dachneigung": ["[30]", "[45]"],
                "Dachorientierung": ["[180]", "[90]"],
                "Dachflaeche": ["[100]", "[200]"],
            },
            crs="EPSG:25832",
        )

    @pytest.fixture
    def region(self):
        return gpd.GeoDataFrame(
            {
                "geometry": [Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1)])],
            },
            crs="EPSG:25832",
        )

    def test_clips_to_region(self, buildings, region):
        clipped = clip_buildings_to_region(buildings, region)
        assert len(clipped) == 1  # only the first building intersects

    def test_roof_params_parsed(self, buildings, region):
        clipped = clip_buildings_to_region(buildings, region)
        assert "Dachneigung" in clipped.columns
        assert clipped["Dachneigung"].iloc[0] == 30

    def test_no_intersection(self, buildings):
        far_region = gpd.GeoDataFrame(
            {
                "geometry": [Polygon([(100, 100), (100, 101), (101, 101), (101, 100)])],
            },
            crs="EPSG:25832",
        )
        clipped = clip_buildings_to_region(buildings, far_region)
        assert len(clipped) == 0

    def test_empty_buildings(self):
        empty = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:25832")
        region = gpd.GeoDataFrame(
            {"geometry": [Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])]},
            crs="EPSG:25832",
        )
        with pytest.raises(ValueError, match="empty"):
            clip_buildings_to_region(empty, region)


class TestAverageRoofParams:
    @pytest.fixture
    def buildings(self):
        return gpd.GeoDataFrame(
            {
                "geometry": [
                    Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
                    Polygon([(2, 2), (2, 3), (3, 3), (3, 2)]),
                ],
                "Dachneigung": [30, 50],
                "Dachorientierung": [180, 90],
            },
            crs="EPSG:25832",
        )

    def test_average_degrees(self, buildings):
        slope, azim = average_roof_params(buildings)
        assert slope == pytest.approx(40.0)
        assert azim == pytest.approx(135.0)

    def test_empty_buildings(self):
        empty = gpd.GeoDataFrame(
            {"geometry": [], "Dachneigung": [], "Dachorientierung": []},
            crs="EPSG:25832",
        )
        with pytest.raises(ValueError, match="empty"):
            average_roof_params(empty)

    def test_missing_column(self, buildings):
        bad = buildings.drop(columns=["Dachneigung"])
        with pytest.raises(KeyError):
            average_roof_params(bad)
