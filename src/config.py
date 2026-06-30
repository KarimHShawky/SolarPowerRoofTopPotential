from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RegionConfig:
    name: str = "Leeste"
    shapefile: str = "data/leeste3035.gpkg"
    nuts: str | None = "data/NUTS_RG_10M_2021_4326.geojson"
    crs: int = 3035


@dataclass
class DataConfig:
    builtup_raster: str | None = "data/IBU_2018_010m_eu_03035_V1_0.tif"
    lod2_tiles: list[str] = field(
        default_factory=lambda: [
            "data/lod2_1.gpkg",
            "data/lod2_2.gpkg",
            "data/lod2_3.gpkg",
        ]
    )
    demand: str = "data/Last_240222.csv"
    cop: str = "data/COP_WP.xlsx"
    cutout: str = "data/era5-{year}-{region}.nc"


@dataclass
class ParametersConfig:
    year: int = 2014
    capacity_density: float = 19.0
    st_efficiency_ratio: list[float] = field(default_factory=lambda: [25, 60])
    st_model: str = "atlite"
    st_c0: float = 0.8
    st_c1: float = 3.0
    st_t_store: float = 80.0
    st_eta_0: float = 0.73
    st_a_1: float = 1.7
    st_a_2: float = 0.016
    st_temp_inlet: float = 20.0
    st_delta_temp_n: float = 10.0
    st_pv_power_density: float = 200.0  # W/m², PV panel density for m² ↔ MW conversion
    footprint_to_roof: float = 1.0  # OSM: fraction of building footprint → usable roof
    pv_type: str = "CdTe"
    hp_type: str = "air_source"
    alpha_values: list[float] = field(
        default_factory=lambda: [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    )
    resolution: float = 5.0
    buffer: float = 0.005


@dataclass
class Config:
    region: RegionConfig = field(default_factory=RegionConfig)
    data: DataConfig = field(default_factory=DataConfig)
    parameters: ParametersConfig = field(default_factory=ParametersConfig)
    base_dir: str = "."

    @property
    def base_path(self) -> Path:
        return Path(self.base_dir).resolve()

    def resolve_path(self, path: str) -> Path:
        return self.base_path / path


def load_config(path: str | Path) -> Config:
    """Load configuration from a YAML file, falling back to defaults."""
    import yaml

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        logger.warning("Empty config file — using defaults")
        return Config()

    cfg = Config()

    if "base_dir" in raw:
        cfg.base_dir = raw["base_dir"]

    if "region" in raw:
        r = raw["region"]
        if "name" in r:
            cfg.region.name = r["name"]
        if "shapefile" in r:
            cfg.region.shapefile = r["shapefile"]
        if "nuts" in r:
            cfg.region.nuts = r["nuts"]
        if "crs" in r:
            cfg.region.crs = r["crs"]

    if "data" in raw:
        d = raw["data"]
        if "builtup_raster" in d:
            cfg.data.builtup_raster = d["builtup_raster"]
        if "lod2_tiles" in d:
            cfg.data.lod2_tiles = d["lod2_tiles"]
        if "demand" in d:
            cfg.data.demand = d["demand"]
        if "cop" in d:
            cfg.data.cop = d["cop"]
        if "cutout" in d:
            cfg.data.cutout = d["cutout"]

    if "parameters" in raw:
        p = raw["parameters"]
        if "year" in p:
            cfg.parameters.year = p["year"]
        if "capacity_density" in p:
            cfg.parameters.capacity_density = p["capacity_density"]
        if "st_efficiency_ratio" in p:
            cfg.parameters.st_efficiency_ratio = p["st_efficiency_ratio"]
        if "st_model" in p:
            cfg.parameters.st_model = p["st_model"]
        if "st_c0" in p:
            cfg.parameters.st_c0 = p["st_c0"]
        if "st_c1" in p:
            cfg.parameters.st_c1 = p["st_c1"]
        if "st_t_store" in p:
            cfg.parameters.st_t_store = p["st_t_store"]
        if "st_eta_0" in p:
            cfg.parameters.st_eta_0 = p["st_eta_0"]
        if "st_a_1" in p:
            cfg.parameters.st_a_1 = p["st_a_1"]
        if "st_a_2" in p:
            cfg.parameters.st_a_2 = p["st_a_2"]
        if "st_temp_inlet" in p:
            cfg.parameters.st_temp_inlet = p["st_temp_inlet"]
        if "st_delta_temp_n" in p:
            cfg.parameters.st_delta_temp_n = p["st_delta_temp_n"]
        if "st_pv_power_density" in p:
            cfg.parameters.st_pv_power_density = p["st_pv_power_density"]
        if "footprint_to_roof" in p:
            cfg.parameters.footprint_to_roof = p["footprint_to_roof"]
        if "pv_type" in p:
            cfg.parameters.pv_type = p["pv_type"]
        if "hp_type" in p:
            cfg.parameters.hp_type = p["hp_type"]
        if "alpha_values" in p:
            cfg.parameters.alpha_values = p["alpha_values"]
        if "resolution" in p:
            cfg.parameters.resolution = p["resolution"]
        if "buffer" in p:
            cfg.parameters.buffer = p["buffer"]

    return cfg
