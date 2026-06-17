# Setting Up the CDS API for ERA5 Data

The ERA5 weather data is obtained from the Copernicus Climate Data Store (CDS). Access requires a free account and an API key.

## Step 1: Create a CDS Account

1. Go to https://cds.climate.copernicus.eu/user/register
2. Fill in the registration form and verify your email
3. Log in at https://cds.climate.copernicus.eu/

## Step 2: Get Your API Key

1. Visit https://cds.climate.copernicus.eu/api-how-to
2. Your API key is displayed as `{uid}:{api-key}`
3. Create the file `~/.cdsapirc` with the following content:

```
url: https://cds.climate.copernicus.eu/api/v2
key: {uid}:{api-key}
```

Replace `{uid}:{api-key}` with your credentials.

### Example `.cdsapirc`

```
url: https://cds.climate.copernicus.eu/api/v2
key: 12345:abcdef12-3456-7890-abcd-ef1234567890
```

## Step 3: Accept the ERA5 Licence

1. Go to the ERA5 dataset page: https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-single-levels
2. Click "Download data"
3. Accept the terms of use (once per account)

## Step 4: Verify the Connection

Run this test in Python:

```python
import cdsapi
c = cdsapi.Client()
c.retrieve(
    "reanalysis-era5-single-levels",
    {
        "product_type": "reanalysis",
        "variable": "2m_temperature",
        "year": "2014",
        "month": "01",
        "day": "01",
        "time": "00:00",
        "format": "netcdf",
    },
    "test.nc",
)
```

If this works, the API is properly configured.

## Step 5: Download Weather Data

In the notebooks, uncomment the `cutout.prepare()` line:

```python
cutout = atlite.Cutout(
    path="data/era5-2014-leeste.nc",
    module="era5",
    x=x_slice,
    y=y_slice,
    time="2014",
    weather=True,
)
cutout.prepare()  # <-- uncomment this line
```

The first download may take **30–60 minutes** depending on the region size and your connection speed. Subsequent runs reuse the cached `.nc` file.

## Troubleshooting

| Problem | Solution |
|---|---|
| `401 Unauthorized` | Check your API key in `~/.cdsapirc` |
| `403 Forbidden` | You haven't accepted the ERA5 licence terms |
| `404 Not Found` | The dataset name may have changed; check the CDS catalogue |
| Slow download | Reduce the region size or use a coarser spatial resolution |
