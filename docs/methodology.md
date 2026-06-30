# Methodology

This document describes the calculations performed in the SolarPowerRoofTopPotential notebooks.

---

## 1. Overview

The tool computes two energy potentials for a given region:

1. **Solar Thermal (ST)** — flat-plate collectors on rooftops, providing heat for domestic hot water
2. **Photovoltaic (PV) + Heat Pump (HP)** — PV panels powering air-source heat pumps for space heating

A sensitivity parameter $\alpha$ (0 to 1) controls how roof area is split between these two technologies.

---

## 2. Data Flow

```
ERA5 Weather Data  ──┐
                     ├──> atlite Cutout ──> Solar Thermal Model ──> Solar Thermal (MW)
Building Footprints ─┤                     (atlite or oemof)
                     ├──> ExclusionContainer ──> Availability Matrix ──> Capacity Matrix
Region Shape ───────┘                            │                       │
                                                  │                       └── ÷ st_pv_power_density
                                                  │                            └──> Collector Area (m²)
                                                  └──> PV simulation ──> PV × COP ──> HP Thermal
```

---

## 3. Step-by-Step

### 3.1 ERA5 Weather Data

ERA5 reanalysis data provides hourly global, direct, and diffuse irradiance, temperature, and wind speed for the region. The `atlite` library manages downloading (via CDS API) and processing.

### 3.2 Building Footprints

Three approaches identify where solar installations can be placed:

**Raster approach** (⚠️ Legacy): A binary built-up area raster (e.g. Copernicus High Resolution Layer Imperviousness) marks building pixels. atlite's `ExclusionContainer` uses this to determine which grid cells contain buildings. Includes roads and parking areas.

**LoD2 approach** (Benchmark): 3D building models provide precise roof geometry. The vector footprints are rasterized to a GeoTIFF, then used with `ExclusionContainer`. Roof slope (`Dachneigung`), azimuth (`Dachorientierung`), and area (`Dachflaeche`) are extracted from the building attributes.

**OSM approach** (Recommended fallback): Building footprints from OpenStreetMap are downloaded via `osmnx` or from Geofabrik. Vector footprints are rasterized identically to LoD2. Since OSM lacks roof geometry, a single `footprint_to_roof` parameter maps footprint area to equivalent panel-covered area, calibrated from LoD2 benchmarks.

### 3.3 Availability Matrix

The availability matrix ($A$) represents the fraction of each ERA5 grid cell that is available for solar installation:

$$A_{i,j} = \text{fraction of grid cell } (i,j) \text{ covered by buildings}$$

The capacity matrix converts this to installable power:

$$C_{i,j} = A_{i,j} \cdot \text{Area}_{i,j} \cdot \text{cap\_per\_sqkm}$$

where `cap_per_sqkm` is a capacity density (MW/km²): **8 MW/km²** for the raster approach (calibrated via Solarkataster Diepholz, Shawky 2024), **19 MW/km²** for the LoD2 approach (LoD2-derived after applying a coverage ratio, see below).

For the OSM approach, the same capacity matrix formula applies, but the area refers to OSM building footprint area instead of LoD2 roof area. The calibration uses a `footprint_to_roof` parameter that converts OSM footprint area to an equivalent panel-covered area, derived from the LoD2 benchmark.

The capacity density is not a free parameter. It is derived from the panel power density and an empirically calibrated coverage ratio:

$$\text{cap\_per\_sqkm} = \text{coverage\_ratio} \times p_{\text{pv\_density}}$$

where $\text{coverage\_ratio} = 0.095$ (9.5 %) and $p_{\text{pv\_density}} = 200\ \text{W/m}^2$. This means: for every km² of LoD2 rasterised building area, 0.095 km² (9.5 %) is assumed to be covered by PV panels at 200 W/m² peak density. The 9.5 % bundles the combined effect of setbacks, wiring gaps, non-ideal orientations, and non-installation across the region.

The capacity matrix represents PV nameplate capacity. For solar thermal, the corresponding collector area is recovered from the PV panel power density:

$$A_{\text{coll}} = C \,/\, p_{\text{pv\_density}}$$

where $p_{\text{pv\_density}} = 200\ \text{W/m}^2$ (default, configurable via `st_pv_power_density`). This recovers the *implicit* panel-covered area from the capacity matrix — approximately 3,370 m² for the Leeste LoD2 case and 3,370 m² for the OSM case (via `footprint_to_roof = 0.037`).

### 3.4 Solar Thermal — Flat-Plate Collector Models

Two flat-plate collector models are available, selectable via `st_model` in the configuration:

| Model | Formula | Reference | Use Case |
|-------|---------|-----------|----------|
| `atlite` (default) | $\eta = c_0 - c_1 \frac{T_{\text{store}} - T_{\text{amb}}}{G_{\text{tilted}}}$ | Henning & Palzer (2014) | General use, DHW-scale |
| `oemof` | $\eta = \eta_0 - a_1 \frac{\Delta T}{G} - a_2 \frac{\Delta T^2}{G}$ | EN 12975 | Higher accuracy, specific collector datasheets |

where $\Delta T = T_{\text{inlet}} + \Delta T_n - T_{\text{amb}}$.

**Model A — atlite (Henning & Palzer 2014)**

Uses atlite's built-in `cutout.solar_thermal()` method. The collector efficiency is linear in temperature difference:

$$\eta(t) = c_0 - c_1 \times \frac{T_{\text{store}} - T_{\text{amb}}(t)}{G_{\text{tilted}}(t)}$$

The irradiance on the tilted collector surface $G_{\text{tilted}}$ is computed from ERA5 global horizontal irradiance (GHI = `influx_direct + influx_diffuse`) and diffuse horizontal irradiance (DHI = `influx_diffuse`) using atlite's solar position and tilted irradiation models.

The heat output is:

$$P_{\text{ST}}(t) = A_{\text{coll}} \times G_{\text{tilted}}(t) \times \eta(t)$$

where $A_{\text{coll}} = C \,/\, p_{\text{pv\_density}}$ is the collector area (m²) derived from the PV capacity matrix $C$ and the PV panel power density $p_{\text{pv\_density}}$.

Default parameters: $c_0 = 0.8$, $c_1 = 3.0\ \text{W/m}^2\text{K}$, $T_{\text{store}} = 80\ ^\circ\text{C}$.

**Model B — oemof (EN 12975 quadratic)**

Uses the quadratic collector efficiency model from the European standard EN 12975, also implemented by `oemof.thermal.solar_thermal_collector`:

$$\eta(t) = \eta_0 - a_1 \frac{\Delta T(t)}{G_{\text{tilted}}(t)} - a_2 \frac{\Delta T(t)^2}{G_{\text{tilted}}(t)}$$

The calculation uses the same ERA5 irradiance and temperature data, with atlite handling the spatial aggregation via its `convert_and_aggregate` framework, while applying the quadratic efficiency formula.

Default parameters (typical flat-plate collector): $\eta_0 = 0.73$, $a_1 = 1.7\ \text{W/m}^2\text{K}$, $a_2 = 0.016\ \text{W/m}^2\text{K}^2$, $T_{\text{inlet}} = 20\ ^\circ\text{C}$, $\Delta T_n = 10\ \text{K}$.

**Comparison to previous approach**

Previously, solar thermal was approximated from parabolic trough CSP output:

$$P_{\text{CSP}}(t) = \text{atlite.csp}(t)$$

$$P_{\text{ST}}(t) = P_{\text{CSP}}(t) \times \frac{25}{60}$$

The CSP model only uses direct normal irradiance (DNI) and assumes a constant efficiency ratio. The new flat-plate models use both direct and diffuse radiation and include temperature-dependent efficiency, providing more accurate seasonal and diurnal patterns.

Additionally, the old formula recovered collector area from `capacity_density` (MW/km²), giving the full built-up area rather than the usable roof fraction. The new conversion via `st_pv_power_density` (W/m²) recovers the actual panel/collector area, eliminating a ~25× systematic overestimate (e.g. 428,000 m² → 17,100 m² for the Leeste raster case).

### 3.5 Photovoltaic Simulation

atlite simulates **CdTe thin-film PV panels**:

$$P_{\text{PV}}(t) = \text{atlite.pv}(t, \text{orientation})$$

- **Raster approach**: `orientation = "latitude_optimal"` — panels at the ideal tilt
- **LoD2 approach**: `orientation = dict(slope=avg_slope, azimuth=avg_azimuth)` — panels follow actual roof orientation

### 3.6 Heat Pump

Hourly PV electricity drives air-source heat pumps:

$$P_{\text{HP}}(t) = P_{\text{PV}}(t) \times \text{COP}(t)$$

COP depends on ambient temperature: higher when warm, lower when cold.

### 3.7 Load Coverage

The thermal output is compared to demand:

- Solar thermal covers domestic hot water demand
- Heat pump covers space heating demand

$$\text{Coverage}_{\text{DHW}} = \frac{\sum P_{\text{ST}}(t)}{\sum \text{DHW}(t)} \times 100\%$$

$$\text{Coverage}_{\text{SH}} = \frac{\sum P_{\text{HP}}(t)}{\sum \text{SH}(t)} \times 100\%$$

### 3.8 Sensitivity Analysis

The parameter $\alpha$ allocates roof area:

| $\alpha$ | PV allocation | ST allocation |
|---|---|---|
| 0.0 | 0% | 100% |
| 0.2 | 20% | 80% |
| 0.4 | 40% | 60% |
| 0.6 | 60% | 40% |
| 0.8 | 80% | 20% |
| 1.0 | 100% | 0% |

For each $\alpha$:

$$P_{\text{PV,}\alpha}(t) = P_{\text{PV}}(t) \times \alpha$$
$$P_{\text{ST,}\alpha}(t) = P_{\text{ST}}(t) \times (1 - \alpha)$$
$$P_{\text{HP,}\alpha}(t) = P_{\text{PV,}\alpha}(t) \times \text{COP}(t)$$

**Overproduction** occurs when generation exceeds demand at any hour:

$$\text{Overprod}_{\text{DHW}}(\alpha) = \sum \max(0, P_{\text{ST,}\alpha}(t) - \text{DHW}(t))$$
$$\text{Overprod}_{\text{SH}}(\alpha) = \sum \max(0, P_{\text{HP,}\alpha}(t) - \text{SH}(t))$$

### 3.9 oemof Analysis (LoD2 Only)

Pre-computed oemof optimization results show system costs and CO2 emissions for each $\alpha$ scenario. These were generated by a separate energy system model that considers:

- Investment costs for PV, solar thermal, and heat pumps
- Operating costs
- Grid electricity consumption
- CO2 emissions from grid electricity

The results are hardcoded in the notebook as numpy arrays.

---

## 4. Key Assumptions

| Parameter | Raster Approach (⚠️) | LoD2 Approach | OSM Approach |
|---|---|---|---|
| Capacity density | 8 MW/km² | 19 MW/km² | footprint_to_roof × 200 MW/km² (7.4 for Leeste) |
| PV panel power density | 200 W/m² (STC, configurable) | 200 W/m² (STC, configurable) | 200 W/m² (STC, configurable) |
| PV orientation | Latitude-optimal | Average roof slope/azimuth | Latitude-optimal |
| PV panel type | CdTe | CdTe | CdTe |
| ST model | atlite (Henning & Palzer) | atlite (Henning & Palzer) | atlite (Henning & Palzer) |
| Heat pump type | Air-source | Air-source | Air-source |
| Building availability | Statistical (raster) | Geometric (LoD2) | Geographic (OSM footprint → roof) |
| Area calibration | cap_per_sqkm = 8 | cap_per_sqkm = 19 | footprint_to_roof ≈ 0.037 (Leeste) |

---

## 5. References

- `atlite` library: https://atlite.readthedocs.io/
- ERA5: Hersbach et al. (2020), "The ERA5 global reanalysis", *Quarterly Journal of the Royal Meteorological Society*
- Henning & Palzer (2014), "A comprehensive model for solar energy systems", *Energy*
- EN 12975: "Thermal solar systems and components — Solar collectors — Test methods"
- oemof: https://oemof.org/
- LoD2 specification: https://www.adv-online.de/ (German cadastre)
