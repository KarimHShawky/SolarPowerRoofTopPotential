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

Two analysis approaches are provided (see [Choosing Your Approach](#choosing-your-approach)):

| Notebook | Approach | Data Required |
|---|---|---|
| `01_Raster_Approach.ipynb` | Built-up area raster (GeoTIFF) | Land cover / imperviousness raster |
| `02_LoD2_Approach.ipynb` | LoD2 3D building models | LoD2 building footprints with roof geometry |

---

## Methodology

**Solar Thermal Potential** — atlite simulates parabolic trough CSP (concentrated solar power) using ERA5 direct normal irradiance. The CSP output is converted to flat-plate solar thermal using an efficiency ratio (25/60), reflecting typical operating temperatures for building-scale solar thermal collectors.

**Photovoltaic Potential** — atlite simulates CdTe thin-film PV panels. The raster approach uses latitude-optimal orientation; the LoD2 approach uses the actual average roof slope and azimuth from the building data.

**Heat Pump Integration** — hourly PV generation is multiplied by hourly COP values for air-source heat pumps to obtain the thermal output that can be delivered for space heating.

**Sensitivity Analysis** — the parameter $\alpha$ controls the allocation of roof area between PV ($\alpha$) and solar thermal ($1-\alpha$). For each $\alpha$, we compute load coverage and overproduction. The LoD2 notebook also includes **oemof-based** system cost and CO2 emission results.

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
│   ├── data_loading.py           # Load shape, demand, COP, weather data
│   └── lod2_processing.py        # Load & process LoD2 building data
├── notebooks/
│   ├── 01_Raster_Approach.ipynb  # Built-up raster approach
│   └── 02_LoD2_Approach.ipynb    # LoD2 building approach + oemof
├── data/
│   ├── leeste3035.gpkg           # Region shape (Leeste, Germany)
│   ├── NUTS_RG_10M_2021_4326.geojson
│   ├── IBU_2018_010m_eu_03035_V1_0.tif  # Built-up area raster
│   ├── lod2_1.gpkg / 2 / 3       # LoD2 building tiles
│   ├── Last_240222.csv           # Hourly heat demand
│   ├── COP_WP.xlsx               # Heat pump COP values
│   ├── Irradation.csv            # Extra irradiation data
│   └── era5-2014-leeste.nc       # Pre-downloaded ERA5 cutout
└── docs/
    ├── setup_cds_api.md          # ERA5 / CDS API setup guide
    └── methodology.md            # Detailed methodology
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

# Install dependencies
pip install -r requirements.txt
```

### CDS API (ERA5 Data)

To download ERA5 weather data, you need a CDS API key:

1. Register at https://cds.climate.copernicus.eu/user/register
2. Retrieve your API key from https://cds.climate.copernicus.eu/api-how-to
3. Save it to `~/.cdsapirc`:

```
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

Both notebooks are self-contained tutorials with explanatory markdown. Each cell documents what it does and why. The key difference:

- **`01_Raster_Approach.ipynb`** — Start here if you have a land-cover/built-up raster. Simpler setup, works anywhere such data exists.
- **`02_LoD2_Approach.ipynb`** — Use if you have LoD2 building models with roof geometry. More accurate, includes oemof analysis.

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

Calculation logic (atlite calls, CSP → ST conversion, sensitivity analysis) is kept inline in the notebooks rather than in the module, making the methodology fully transparent.

---

## Choosing Your Approach

| Criterion | Raster Approach | LoD2 Approach |
|---|---|---|
| **Data needed** | Built-up area raster (GeoTIFF) | LoD2 building models with roof attributes |
| **PV orientation** | Latitude-optimal (theoretical max) | Actual roof slope & azimuth |
| **Accuracy** | Good (statistical roof availability) | Better (per-building geometry) |
| **Complexity** | Low | Medium |
| **Availability** | Copernicus, USGS, etc. | Germany (ALKIS), Netherlands, Switzerland, some US cities |
| **Extra features** | — | Average roof params, oemof cost/CO2 analysis |

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
