# Multi-year ERA5 Download Tracker

**Leeste LoD2 benchmark** (8.5–9.0 lon, 51.0–53.0 lat · 0.25° · 14 variables)

| # | Year | Cutout | Pipeline | Notes |
|---|------|--------|----------|-------|
| — | 2014 | ✅ | ✅ | Pre-existing (7.1 MB) |
| 1 | 2015 | ✅ | ✅ | 9.0 MB · PV=256.9 MWh · ST=2.4 MWh |
| 2 | 2016 | ✅ | ❌ | 9.1 MB · Complete, pipeline pending |
| 3 | 2017 | 🔄 | ❌ | 3.7 MB · temperature downloading monthly (10/12) |
| 4 | 2018 | ❌ | ❌ | Queued |
| 5 | 2019 | ❌ | ❌ | Queued |
| 6 | 2020 | ❌ | ❌ | Queued |
| 7 | 2021 | ❌ | ❌ | Queued |
| 8 | 2022 | ❌ | ❌ | Queued |
| 9 | 2023 | ❌ | ❌ | Queued |
| 10 | 2024 | ❌ | ❌ | Queued |

**Symbols:** ⬜ Pending · 🔄 In progress · ✅ Complete · ❌ Failed

**Log:** `multi_year_analysis.log`
**Results:** `results/annual_summary.csv`

---

## Validation checks (run after each year finishes)

- [x] Cutout opens with `atlite.Cutout(path=…)`
- [x] All 15 features present
- [x] PV yield magnitude matches 2014 baseline (~0.67 MW capacity)
- [x] No NaN / inf values
- [x] `compute_solar_thermal()` runs without error
