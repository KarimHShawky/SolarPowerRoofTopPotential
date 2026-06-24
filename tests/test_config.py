from pathlib import Path

import pytest
import yaml

from src.config import Config, load_config

FIXTURES_DIR = Path(__file__).resolve().parent.parent


class TestLoadConfig:
    def test_loads_example_config(self):
        path = FIXTURES_DIR / "config.example.yaml"
        cfg = load_config(path)
        assert cfg.region.name == "Leeste"
        assert cfg.parameters.year == 2014
        assert cfg.parameters.capacity_density == 19.0

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config(FIXTURES_DIR / "nonexistent.yaml")

    def test_empty_config(self, tmp_path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        cfg = load_config(empty)
        # Should fall back to defaults
        assert cfg.region.name == "Leeste"
        assert isinstance(cfg, Config)

    def test_partial_config(self, tmp_path):
        partial = tmp_path / "partial.yaml"
        partial.write_text(
            yaml.dump({"region": {"name": "Munich"}, "parameters": {"year": 2020}})
        )
        cfg = load_config(partial)
        assert cfg.region.name == "Munich"
        # Defaults for unspecified fields
        assert cfg.parameters.capacity_density == 19.0
        assert cfg.region.crs == 3035
        assert cfg.data.demand == "data/Last_240222.csv"


class TestConfigDefaults:
    def test_default_config(self):
        cfg = Config()
        assert cfg.region.name == "Leeste"
        assert cfg.parameters.year == 2014
        assert cfg.parameters.capacity_density == 19.0
        assert cfg.parameters.alpha_values == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        assert cfg.data.lod2_tiles == [
            "data/lod2_1.gpkg",
            "data/lod2_2.gpkg",
            "data/lod2_3.gpkg",
        ]

    def test_resolve_path(self):
        cfg = Config(base_dir="/some/project")
        resolved = cfg.resolve_path("data/file.csv")
        assert resolved == Path("/some/project/data/file.csv")

    def test_base_path_property(self):
        cfg = Config(base_dir="/tmp")
        assert cfg.base_path == Path("/tmp").resolve()
