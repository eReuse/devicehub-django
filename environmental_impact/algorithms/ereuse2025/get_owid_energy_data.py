import io
import json
import os

import pandas as pd
import requests

from environmental_impact.algorithms.country_codes import alpha3_to_alpha2


OWID_CSV_URL = "https://ourworldindata.org/grapher/carbon-intensity-electricity.csv"
OUTPUT_FILENAME = "latest_carbon_intensity_by_country.json"


def fetch_latest_carbon_intensity_data(url: str = OWID_CSV_URL) -> dict[str, float]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    dataframe = pd.read_csv(io.StringIO(response.text))
    dataframe = dataframe.dropna(subset=["Code", "Carbon intensity of electricity per kWh"])
    dataframe = dataframe[dataframe["Code"].str.len() == 3].copy()

    latest_indices = dataframe.groupby("Code")["Year"].idxmax()
    latest_data = dataframe.loc[latest_indices, ["Code", "Carbon intensity of electricity per kWh"]]

    return {
        alpha3_to_alpha2(code): round(float(value), 3)
        for code, value in latest_data.itertuples(index=False)
        if alpha3_to_alpha2(code)
    }


def save_latest_carbon_intensity_data(output_path: str | None = None) -> str:
    if not output_path:
        output_path = os.path.join(os.path.dirname(__file__), OUTPUT_FILENAME)
    data = fetch_latest_carbon_intensity_data()
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(data, output_file, sort_keys=True, indent=2)
    return output_path


if __name__ == "__main__":
    save_latest_carbon_intensity_data()
