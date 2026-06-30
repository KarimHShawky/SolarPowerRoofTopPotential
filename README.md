# SolarPowerRoofTopPotential

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A tool to calculate the **rooftop solar energy potential** (solar thermal and photovoltaic) based on historical ERA5 weather data and open-source geodata. Includes sensitivity analysis of the PV-to-solar-thermal allocation ratio and integration with the [oemof](https://oemof.org/) energy system optimization framework.

---

## Table of Contents

- [Overview](#overview)
- [Methodology](#methodology)
- [Repository Structure](#repository-structure)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [CDS API (ERA5 Data)](#cds-api-era5-data)
- [Usage](#usage)
  - [Notebooks](#notebooks)
  - [As a Python Module](#as-a-python-module)
- [Choosing Your Approach](#choosing-your-approach)
- [Input Data](#input-data)
- [Outputs](#outputs)
- [Citation](#citation)
- [License](#license)

---

## Overview

This tool computes the potential for rooftop solar thermal and PV-powered heat pump systems for a given region. It uses:

- **ERA5 reanalysis weather data** (via the `atlite` library)
- **Open-source geodata**: either a built-up area raster (e.g. Copernicus imperviousness) or **LoD2 building models** with actual roof geometry
- **Simulated hourly heat demand** for domestic hot water (DHW) and space heating (SH)
- **COP values** for air-source heat pumps

Three analysis approaches are provided (see [Choosing Your Approach](#choosing-your-approach)):

| Notebook | Approach | Data Required |
|---|---|---|
| `01_Raster_Approach.ipynb` ⚠️ | Built-up area raster (GeoTIFF) — **legacy**, kept for reproducibility | Imperviousness raster |
| `02_LoD2_Approach.ipynb` | LoD2 3D building models — **benchmark** | LoD2 building footprints with roof geometry |
| `03_OSM_Approach.ipynb` | OSM building footprints — **recommended fallback** | OSM buildings (osmnx / Geofabrik) |

---

## Methodology

**Solar Thermal Potential** — Two flat-plate collector models, selectable via `st_model` in the config:
- `atlite` (default): linear efficiency model (Henning & Palzer 2014) — uses atlite's built-in `cutout.solar_thermal()`
- `oemof`: quadratic EN 12975 model — same irradiance transposition via atlite, with the European standard efficiency formula

Both models use ERA5 global + diffuse irradiance (not just DNI like CSP) and include temperature-dependent efficiency. Collector area is derived from the PV capacity matrix via `st_pv_power_density` (default 200 W/m²).

**Photovoltaic Potential** — atlite simulates CdTe thin-film PV panels. The raster approach uses latitude-optimal orientation; the LoD2 approach uses the actual average roof slope and azimuth from the building data.

**Heat Pump Integration** — hourly PV generation is multiplied by hourly COP values for air-source heat pumps to obtain the thermal output that can be delivered for space heating.

**Sensitivity Analysis** — the parameter $\alpha$ controls the allocation of roof area between PV ($\alpha$) and solar thermal ($1-\alpha$). For each $\alpha$, we compute load coverage and overproduction. The LoD2 notebook also includes **oemof-based** system cost and CO2 emission results.

All calculations are config-driven via `config.yaml`. See [`config.example.yaml`](config.example.yaml) for all parameters.

See [`docs/methodology.md`](docs/methodology.md) for a detailed walkthrough.

---

## Repository Structure

```
SolarPowerRoofTopPotential/
├── README.md                     # This file
├── LICENSE                       # MIT License
├── requirements.txt              # Python dependencies
├── .gitignore
├── CITATION.cff                  # Citation metadata
├── pyproject.toml                # Minimal package config
├── src/
│   ├── __init__.py
│   ├── config.py                 # Configuration loading (YAML)
│   ├── data_loading.py           # Load shape, demand, COP, weather data
│   ├── lod2_processing.py        # Load & process LoD2 building data
│   ├── osm_processing.py         # Download OSM buildings, clip, rasterize
│   └── solar_thermal.py          # Flat-plate collector models (atlite / oemof)
├── notebooks/
│   ├── 01_Raster_Approach.ipynb  # Built-up raster approach
│   ├── 02_LoD2_Approach.ipynb    # LoD2 building approach + oemof
│   └── 03_OSM_Approach.ipynb     # OSM building footprint approach
├── data/
│   ├── leeste3035.gpkg           # Region shape (Leeste, Germany)
│   ├── NUTS_RG_10M_2021_4326.geojson
│   ├── IBU_2018_010m_eu_03035_V1_0.tif  # Built-up area raster
│   ├── lod2_1.gpkg / 2 / 3       # LoD2 building tiles
│   ├── Last_240222.csv           # Hourly heat demand
│   ├── COP_WP.xlsx               # Heat pump COP values
│   ├── Irradiation.csv            # Extra irradiation data
│   ├── osm_leeste.gpkg           # Pre-downloaded OSM building footprints (280 buildings)
│   └── era5-2014-leeste.nc       # Pre-downloaded ERA5 cutout
├── analysis/
│   ├── multi_year_analysis.py   # 2015–2024 ERA5 sweep script
│   ├── uncertainty_quantification.py  # MC / LHS sensitivity analysis
│   ├── validate_cutout_format.py      # Post-download validation
│   ├── download_tracker.md            # Download status per year
│   └── results/                       # Saved CSVs and plots
├── config.example.yaml         # Documented defaults for all parameters
└── docs/
    ├── setup_cds_api.md         # ERA5 / CDS API setup guide
    └── methodology.md           # Detailed methodology
```

---

## Setup

### Prerequisites

- Python 3.10 or later
- [CDS API account](https://cds.climate.copernicus.eu/) (free, required to download ERA5 data)

### Installation

```bash
# Clone or navigate to the repository
cd SolarPowerRoofTopPotential

# (Recommended) Create a virtual environment
python -m venv venv
source venv/bin/activate   # Linux/MacOS

# Install core dependencies
pip install -r requirements.txt

# (Optional) Install oemof model support for solar thermal
pip install ".[oemof]"
```

### CDS API (ERA5 Data)

To download ERA5 weather data, you need a CDS API key:

1. Register at https://cds.climate.copernicus.eu/user/register
2. Retrieve your API key from https://cds.climate.copernicus.eu/api-how-to
3. Save it to `~/.cdsapirc`:

```yaml
url: https://cds.climate.copernicus.eu/api/v2
key: {uid}:{api-key}
```

See [`docs/setup_cds_api.md`](docs/setup_cds_api.md) for detailed instructions.

---

## Usage

### Notebooks

Run the notebooks from the repository root:

```bash
jupyter notebook notebooks/
```

All three notebooks are self-contained tutorials with explanatory markdown:

- **`01_Raster_Approach.ipynb`** ⚠️ Legacy — Land-cover/built-up raster. Includes roads/parking in roof area. Kept for reproducibility
- **`02_LoD2_Approach.ipynb`** — LoD2 building models with roof geometry (benchmark). Most accurate, includes oemof analysis
- **`03_OSM_Approach.ipynb`** — OSM building footprints (recommended for broad coverage). Downloads data on demand via `osmnx`

### As a Python Module

The `src/` module provides reusable functions for data loading. You can write your own scripts:

```python
from src.data_loading import load_shape, load_demand, load_cop, load_cutout
from src.lod2_processing import load_lod2_buildings, clip_buildings_to_region, average_roof_params

# Load data
shape = load_shape("data/leeste3035.gpkg")
load_dhw, load_sph = load_demand("data/Last_240222.csv")
cop = load_cop("data/COP_WP.xlsx")

# Build your own analysis pipeline from here
```

Solar thermal calculation is provided by `src.solar_thermal.compute_solar_thermal()`. The module supports two collector models (see [Methodology](#methodology)). PV and HP logic and the sensitivity loop are kept in the notebooks.

You can also run from the command line:
```bash
solar-tool run --config config.yaml                 # Single run
solar-tool sweep --config config.yaml --years 2000..2020  # Multi-year sweep
```

---

## Choosing Your Approach

| Criterion | LoD2 Approach (benchmark) | OSM Approach (recommended) | Raster Approach (legacy) |
|---|---|---|---|
| **Data needed** | LoD2 building models with roof attributes | OSM building footprints (downloaded via osmnx) | Built-up area raster (GeoTIFF) |
| **PV orientation** | Actual roof slope & azimuth | Latitude-optimal (no roof plane data) | Latitude-optimal (theoretical max) |
| **Accuracy** | Best (per-building geometry) | Good (footprint-to-roof correction) | Moderate (imperviousness includes roads) |
| **Complexity** | Medium | Low | Low |
| **Availability** | Germany, NL, CH, some US cities | **Global** (OSM coverage) | Copernicus, USGS, etc. |
| **Extra features** | Average roof params, oemof cost/CO2 | — | — |

---

## Input Data

The example uses data for the **Leeste** region in Germany:

| File | Source | Description |
|---|---|---|
| `leeste3035.gpkg` | — | Region boundary (EPSG:3035) |
| `IBU_2018_010m_eu_03035_V1_0.tif` | Copernicus | Built-up area 2018, 10 m resolution |
| `lod2_*.gpkg` | German cadastre (ALKIS) | LoD2 building models with Dachneigung, Dachorientierung, Dachflaeche |
| `NUTS_RG_10M_2021_4326.geojson` | Eurostat | European NUTS administrative regions |
| `Last_240222.csv` | Simulated | Hourly DHW and SH demand for 3 building types |
| `COP_WP.xlsx` | Manufacturer data | Hourly COP for air-source heat pumps |
| `era5-2014-leeste.nc` | ERA5 (Copernicus) | Pre-downloaded weather cutout for 2014 |

Replace these with your own data for other regions.

---

## Outputs

When run successfully, the notebooks produce:

1. **Console output**: load coverage percentages and sensitivity analysis tables
2. **Plots**: time-series of potentials, loads, mismatches (raw + daily resampled), and sensitivity analysis charts
3. **(Commented) file exports**: save plots as PNG/PDF for publications

---

## Citation

If you use this tool in academic work, please cite:

```bibtex
@software{shawky_solar_2024,
  author = {Shawky, Karim},
  title = {SolarPowerRoofTopPotential},
  year = {2024},
  url = {https://github.com/kShawky/SolarPowerRoofTopPotential},
  license = {MIT}
}
```

---

## License

MIT License — see [LICENSE](LICENSE).
