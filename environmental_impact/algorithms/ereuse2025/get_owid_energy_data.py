import io
import json
import os

import pandas as pd
import requests


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


def alpha3_to_alpha2(country_code: str) -> str | None:
    mapping = {
        "AFG": "AF", "ALB": "AL", "DZA": "DZ", "ASM": "AS", "AGO": "AO",
        "ATG": "AG", "ARG": "AR", "ARM": "AM", "ABW": "AW", "AUS": "AU",
        "AUT": "AT", "AZE": "AZ", "BHS": "BS", "BHR": "BH", "BGD": "BD",
        "BRB": "BB", "BLR": "BY", "BEL": "BE", "BLZ": "BZ", "BEN": "BJ",
        "BMU": "BM", "BTN": "BT", "BOL": "BO", "BIH": "BA", "BWA": "BW",
        "BRA": "BR", "VGB": "VG", "BRN": "BN", "BGR": "BG", "BFA": "BF",
        "BDI": "BI", "KHM": "KH", "CMR": "CM", "CAN": "CA", "CPV": "CV",
        "CYM": "KY", "CAF": "CF", "TCD": "TD", "CHL": "CL", "CHN": "CN",
        "COL": "CO", "COM": "KM", "COG": "CG", "COD": "CD", "COK": "CK",
        "CRI": "CR", "CIV": "CI", "HRV": "HR", "CUB": "CU", "CYP": "CY",
        "CZE": "CZ", "DNK": "DK", "DJI": "DJ", "DMA": "DM", "DOM": "DO",
        "ECU": "EC", "EGY": "EG", "SLV": "SV", "GNQ": "GQ", "ERI": "ER",
        "EST": "EE", "SWZ": "SZ", "ETH": "ET", "FRO": "FO", "FJI": "FJ",
        "FIN": "FI", "FRA": "FR", "GUF": "GF", "PYF": "PF", "GAB": "GA",
        "GMB": "GM", "GEO": "GE", "DEU": "DE", "GHA": "GH", "GIB": "GI",
        "GRC": "GR", "GRL": "GL", "GRD": "GD", "GLP": "GP", "GUM": "GU",
        "GTM": "GT", "GIN": "GN", "GNB": "GW", "GUY": "GY", "HTI": "HT",
        "HND": "HN", "HKG": "HK", "HUN": "HU", "ISL": "IS", "IND": "IN",
        "IDN": "ID", "IRN": "IR", "IRQ": "IQ", "IRL": "IE", "ISR": "IL",
        "ITA": "IT", "JAM": "JM", "JPN": "JP", "JOR": "JO", "KAZ": "KZ",
        "KEN": "KE", "KIR": "KI", "XKX": "XK", "KWT": "KW", "KGZ": "KG",
        "LAO": "LA", "LVA": "LV", "LBN": "LB", "LSO": "LS", "LBR": "LR",
        "LBY": "LY", "LTU": "LT", "LUX": "LU", "MAC": "MO", "MDG": "MG",
        "MWI": "MW", "MYS": "MY", "MDV": "MV", "MLI": "ML", "MLT": "MT",
        "MTQ": "MQ", "MRT": "MR", "MUS": "MU", "MEX": "MX", "FSM": "FM",
        "MDA": "MD", "MNG": "MN", "MNE": "ME", "MSR": "MS", "MAR": "MA",
        "MOZ": "MZ", "MMR": "MM", "NAM": "NA", "NRU": "NR", "NPL": "NP",
        "NLD": "NL", "NCL": "NC", "NZL": "NZ", "NIC": "NI", "NER": "NE",
        "NGA": "NG", "NIU": "NU", "PRK": "KP", "MKD": "MK", "MNP": "MP",
        "NOR": "NO", "OMN": "OM", "PAK": "PK", "PSE": "PS", "PAN": "PA",
        "PNG": "PG", "PRY": "PY", "PER": "PE", "PHL": "PH", "POL": "PL",
        "PRT": "PT", "PRI": "PR", "QAT": "QA", "REU": "RE", "ROU": "RO",
        "RUS": "RU", "RWA": "RW", "SHN": "SH", "KNA": "KN", "LCA": "LC",
        "SPM": "PM", "VCT": "VC", "WSM": "WS", "STP": "ST", "SAU": "SA",
        "SEN": "SN", "SRB": "RS", "SYC": "SC", "SLE": "SL", "SGP": "SG",
        "SVK": "SK", "SVN": "SI", "SLB": "SB", "SOM": "SO", "ZAF": "ZA",
        "KOR": "KR", "SSD": "SS", "ESP": "ES", "LKA": "LK", "SDN": "SD",
        "SUR": "SR", "SWE": "SE", "CHE": "CH", "SYR": "SY", "TWN": "TW",
        "TJK": "TJ", "TZA": "TZ", "THA": "TH", "TGO": "TG", "TON": "TO",
        "TTO": "TT", "TUN": "TN", "TUR": "TR", "TKM": "TM", "TCA": "TC",
        "TUV": "TV", "UGA": "UG", "UKR": "UA", "ARE": "AE", "GBR": "GB",
        "USA": "US", "VIR": "VI", "URY": "UY", "UZB": "UZ", "VUT": "VU",
        "VEN": "VE", "VNM": "VN", "ESH": "EH", "YEM": "YE", "ZMB": "ZM",
        "ZWE": "ZW",
    }
    return mapping.get(country_code)


def save_latest_carbon_intensity_data(output_path: str | None = None) -> str:
    if not output_path:
        output_path = os.path.join(os.path.dirname(__file__), OUTPUT_FILENAME)
    data = fetch_latest_carbon_intensity_data()
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(data, output_file, sort_keys=True, indent=2)
    return output_path


if __name__ == "__main__":
    save_latest_carbon_intensity_data()
