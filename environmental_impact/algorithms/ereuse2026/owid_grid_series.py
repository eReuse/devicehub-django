"""Build ``grid_intensity_series.json`` from Our World in Data.

The eReuse 2026 model needs the carbon intensity of electricity *per year*,
not only the latest value: the first life uses the mean of the six years before
intake and the second life the mean of the years after it (Roura Salietti 2025,
§6.6.1). This script keeps every year since 2000 for every country.

    python environmental_impact/algorithms/ereuse2026/owid_grid_series.py
    python environmental_impact/algorithms/ereuse2026/owid_grid_series.py --csv owid.csv

Stdlib only. Source: Our World in Data, carbon intensity of electricity
(CC BY 4.0), values in g CO2e/kWh, stored here in kg CO2e/kWh.
"""

import argparse
import csv
import io
import json
import os
import sys
import urllib.request

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from environmental_impact.algorithms.country_codes import alpha3_to_alpha2

OWID_CSV_URL = "https://ourworldindata.org/grapher/carbon-intensity-electricity.csv"
OUTPUT_FILENAME = "grid_intensity_series.json"
FIRST_YEAR = 2000

# OWID has published this CSV with long and with short column names.
CODE_COLUMNS = ("Code", "code")
YEAR_COLUMNS = ("Year", "year")
VALUE_COLUMNS = ("Carbon intensity of electricity per kWh", "co2_intensity__gco2_kwh")


def _pick(row: dict, names: tuple) -> str | None:
    for name in names:
        if name in row:
            return row[name]
    return None


def parse_series(csv_text: str) -> dict[str, dict[str, float]]:
    series: dict[str, dict[str, float]] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        code, year, value = _pick(row, CODE_COLUMNS), _pick(row, YEAR_COLUMNS), _pick(row, VALUE_COLUMNS)
        if not code or len(code) != 3 or not year or not value:
            continue
        alpha2 = alpha3_to_alpha2(code)
        if not alpha2 or int(year) < FIRST_YEAR:
            continue
        series.setdefault(alpha2, {})[str(int(year))] = round(float(value) / 1000, 4)
    return {code: dict(sorted(years.items())) for code, years in sorted(series.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", help="read a downloaded OWID CSV instead of fetching it")
    args = parser.parse_args()
    if args.csv:
        with open(args.csv, encoding="utf-8") as f:
            text = f.read()
    else:
        with urllib.request.urlopen(OWID_CSV_URL, timeout=60) as resp:
            text = resp.read().decode("utf-8")
    series = parse_series(text)
    output = os.path.join(os.path.dirname(__file__), OUTPUT_FILENAME)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(series, f, separators=(",", ":"), sort_keys=True)
    print(f"{output}: {len(series)} countries")


if __name__ == "__main__":
    main()
