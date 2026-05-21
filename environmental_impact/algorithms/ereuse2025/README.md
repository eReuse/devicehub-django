# Carbon Intensity Data

The file `latest_carbon_intensity_by_country.json` contains the carbon intensity factors (g CO2 / kWh) used by the environmental impact algorithm.

## Source

The data comes from [Our World in Data](https://ourworldindata.org/grapher/carbon-intensity-electricity) and is serialized into the repository to avoid runtime dependencies on external services.

## Updating the data

If you need to refresh the factors with the latest OWID release, run the generator script from this directory:

```bash
python get_owid_energy_data.py
```

### Requirements

- `requests`
- `pandas`

Install them if missing:

```bash
pip install requests pandas
```

### What it does

1. Downloads the latest CSV from OWID.
2. Converts ISO 3166-1 alpha-3 codes to alpha-2.
3. Keeps only the most recent year per country.
4. Overwrites `latest_carbon_intensity_by_country.json`.

After running it, commit the updated JSON file so the new factors are tracked in the repository.
