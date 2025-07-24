import pandas as pd
import requests
import io
import sys
import argparse
import os


def get_iso_code(country_name):
    """
    Converts a country name to its ISO 3166-1 alpha-2 code using a
    comprehensive mapping dictionary. This approach uses only Python builtin
    tools and handles all the non-standard country names used by Our World
    in Data.
    """
    # Comprehensive mapping of OWID country names to ISO 3166-1 alpha-2 codes
    # This includes all valid countries and excludes regional/continental
    # aggregates
    COUNTRY_TO_ISO_MAP = {
        # A
        "Afghanistan": "AF",
        "Albania": "AL",
        "Algeria": "DZ",
        "American Samoa": "AS",
        "Angola": "AO",
        "Antigua and Barbuda": "AG",
        "Argentina": "AR",
        "Armenia": "AM",
        "Aruba": "AW",
        "Australia": "AU",
        "Austria": "AT",
        "Azerbaijan": "AZ",

        # B
        "Bahamas": "BS",
        "Bahrain": "BH",
        "Bangladesh": "BD",
        "Barbados": "BB",
        "Belarus": "BY",
        "Belgium": "BE",
        "Belize": "BZ",
        "Benin": "BJ",
        "Bermuda": "BM",
        "Bhutan": "BT",
        "Bolivia": "BO",
        "Bosnia and Herzegovina": "BA",
        "Botswana": "BW",
        "Brazil": "BR",
        "British Virgin Islands": "VG",
        "Brunei": "BN",
        "Bulgaria": "BG",
        "Burkina Faso": "BF",
        "Burundi": "BI",

        # C
        "Cambodia": "KH",
        "Cameroon": "CM",
        "Canada": "CA",
        "Cape Verde": "CV",
        "Cayman Islands": "KY",
        "Central African Republic": "CF",
        "Chad": "TD",
        "Chile": "CL",
        "China": "CN",
        "Colombia": "CO",
        "Comoros": "KM",
        "Congo": "CG",
        "Cook Islands": "CK",
        "Costa Rica": "CR",
        "Cote d'Ivoire": "CI",
        "Croatia": "HR",
        "Cuba": "CU",
        "Curacao": "CW",
        "Cyprus": "CY",
        "Czechia": "CZ",

        # D
        "Democratic Republic of Congo": "CD",
        "Denmark": "DK",
        "Djibouti": "DJ",
        "Dominica": "DM",
        "Dominican Republic": "DO",

        # E
        "East Timor": "TL",
        "Ecuador": "EC",
        "Egypt": "EG",
        "El Salvador": "SV",
        "Equatorial Guinea": "GQ",
        "Eritrea": "ER",
        "Estonia": "EE",
        "Eswatini": "SZ",
        "Ethiopia": "ET",

        # F
        "Falkland Islands": "FK",
        "Faroe Islands": "FO",
        "Fiji": "FJ",
        "Finland": "FI",
        "France": "FR",
        "French Guiana": "GF",
        "French Polynesia": "PF",

        # G
        "Gabon": "GA",
        "Gambia": "GM",
        "Georgia": "GE",
        "Germany": "DE",
        "Ghana": "GH",
        "Gibraltar": "GI",
        "Greece": "GR",
        "Greenland": "GL",
        "Grenada": "GD",
        "Guadeloupe": "GP",
        "Guam": "GU",
        "Guatemala": "GT",
        "Guinea": "GN",
        "Guinea-Bissau": "GW",
        "Guyana": "GY",

        # H
        "Haiti": "HT",
        "Honduras": "HN",
        "Hong Kong": "HK",
        "Hungary": "HU",

        # I
        "Iceland": "IS",
        "India": "IN",
        "Indonesia": "ID",
        "Iran": "IR",
        "Iraq": "IQ",
        "Ireland": "IE",
        "Israel": "IL",
        "Italy": "IT",

        # J
        "Jamaica": "JM",
        "Japan": "JP",
        "Jordan": "JO",

        # K
        "Kazakhstan": "KZ",
        "Kenya": "KE",
        "Kiribati": "KI",
        "Kosovo": "XK",
        "Kuwait": "KW",
        "Kyrgyzstan": "KG",

        # L
        "Laos": "LA",
        "Latvia": "LV",
        "Lebanon": "LB",
        "Lesotho": "LS",
        "Liberia": "LR",
        "Libya": "LY",
        "Lithuania": "LT",
        "Luxembourg": "LU",

        # M
        "Macao": "MO",
        "Madagascar": "MG",
        "Malawi": "MW",
        "Malaysia": "MY",
        "Maldives": "MV",
        "Mali": "ML",
        "Malta": "MT",
        "Martinique": "MQ",
        "Mauritania": "MR",
        "Mauritius": "MU",
        "Mexico": "MX",
        "Micronesia (country)": "FM",
        "Moldova": "MD",
        "Mongolia": "MN",
        "Montenegro": "ME",
        "Montserrat": "MS",
        "Morocco": "MA",
        "Mozambique": "MZ",
        "Myanmar": "MM",

        # N
        "Namibia": "NA",
        "Nauru": "NR",
        "Nepal": "NP",
        "Netherlands": "NL",
        "Netherlands Antilles": "AN",  # Historical code
        "New Caledonia": "NC",
        "New Zealand": "NZ",
        "Nicaragua": "NI",
        "Niger": "NE",
        "Nigeria": "NG",
        "Niue": "NU",
        "North Korea": "KP",
        "North Macedonia": "MK",
        "Northern Mariana Islands": "MP",
        "Norway": "NO",

        # O
        "Oman": "OM",

        # P
        "Pakistan": "PK",
        "Palestine": "PS",
        "Panama": "PA",
        "Papua New Guinea": "PG",
        "Paraguay": "PY",
        "Peru": "PE",
        "Philippines": "PH",
        "Poland": "PL",
        "Portugal": "PT",
        "Puerto Rico": "PR",

        # Q
        "Qatar": "QA",

        # R
        "Reunion": "RE",
        "Romania": "RO",
        "Russia": "RU",
        "Rwanda": "RW",

        # S
        "Saint Helena": "SH",
        "Saint Kitts and Nevis": "KN",
        "Saint Lucia": "LC",
        "Saint Pierre and Miquelon": "PM",
        "Saint Vincent and the Grenadines": "VC",
        "Samoa": "WS",
        "Sao Tome and Principe": "ST",
        "Saudi Arabia": "SA",
        "Senegal": "SN",
        "Serbia": "RS",
        "Seychelles": "SC",
        "Sierra Leone": "SL",
        "Singapore": "SG",
        "Slovakia": "SK",
        "Slovenia": "SI",
        "Solomon Islands": "SB",
        "Somalia": "SO",
        "South Africa": "ZA",
        "South Korea": "KR",
        "South Sudan": "SS",
        "Spain": "ES",
        "Sri Lanka": "LK",
        "Sudan": "SD",
        "Suriname": "SR",
        "Sweden": "SE",
        "Switzerland": "CH",
        "Syria": "SY",

        # T
        "Taiwan": "TW",
        "Tajikistan": "TJ",
        "Tanzania": "TZ",
        "Thailand": "TH",
        "Togo": "TG",
        "Tonga": "TO",
        "Trinidad and Tobago": "TT",
        "Tunisia": "TN",
        "Turkey": "TR",
        "Turkmenistan": "TM",
        "Turks and Caicos Islands": "TC",
        "Tuvalu": "TV",

        # U
        "Uganda": "UG",
        "Ukraine": "UA",
        "United Arab Emirates": "AE",
        "United Kingdom": "GB",
        "United States": "US",
        "United States Virgin Islands": "VI",
        "Uruguay": "UY",
        "Uzbekistan": "UZ",

        # V
        "Vanuatu": "VU",
        "Venezuela": "VE",
        "Vietnam": "VN",

        # W
        "Western Sahara": "EH",

        # Y
        "Yemen": "YE",

        # Z
        "Zambia": "ZM",
        "Zimbabwe": "ZW",
    }

    # Return the ISO code if the country is in our mapping, otherwise return None
    return COUNTRY_TO_ISO_MAP.get(country_name)


def fetch_and_process_latest_carbon_data(
    url, year_col, value_col, country_col, output_path
):
    """
    Fetches energy data from a URL, finds the most recent carbon intensity
    of electricity for each country, normalizes country to an ISO code,
    and saves the result to a pickle file.

    Args:
        url (str): The URL of the raw CSV file.
        year_col (str): The name of the column containing the year.
        value_col (str): The name of the column containing the carbon intensity data.
        country_col (str): The name of the column containing the country name.
        output_path (str): The path to save the output pickle file.
    """
    try:
        # Step 1: Fetch the data from the URL
        print(f"🔄 Downloading data from '{url}'...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        csv_data = io.StringIO(response.text)

        # Step 2: Load the CSV data into a pandas DataFrame
        print("📊 Loading data into pandas DataFrame...")
        df = pd.read_csv(csv_data)

        # Step 3: Clean the data
        print(f"🧹 Cleaning data: dropping rows with no '{value_col}'...")
        df.dropna(subset=[value_col], inplace=True)

        # Step 4: Find the index of the latest year for each country
        print("🔎 Finding the latest available year for each country...")
        latest_indices = df.groupby(country_col)[year_col].idxmax()
        df_latest = df.loc[latest_indices].copy()

        # Step 5: Normalize country names to ISO alpha-2 codes
        print("🌐 Normalizing country names to ISO alpha-2 codes...")
        df_latest["iso_code"] = df_latest[country_col].apply(get_iso_code)

        # Report on any countries/regions that could not be mapped
        unmapped = df_latest[df_latest["iso_code"].isnull()][country_col].tolist()
        if unmapped:
            print(
                f"⚠️ Could not map the following to ISO codes (they will be excluded): {unmapped}"
            )

        # Drop rows where a code could not be found
        df_latest.dropna(subset=["iso_code"], inplace=True)

        # Step 6: Check if any data remains after processing
        if df_latest.empty:
            print("⚠️ Warning: No data could be processed after normalization.")
            print("The script will exit without creating an output file.")
            return

        # Step 7: Create the final Series with ISO code as the index
        print(f"⚙️ Finalizing data structure with ISO codes as keys...")
        carbon_data = df_latest.set_index("iso_code")
        carbon_intensity_series = carbon_data[value_col]

        # Step 8: Save the final Series to a pickle file
        print(f"💾 Saving the latest carbon intensity data to '{output_path}'...")
        carbon_intensity_series.to_pickle(output_path)

        print(
            f"\n✅ Success! The script finished and saved the data to '{output_path}'."
        )
        print(
            f"   The data contains the latest carbon intensity for {len(carbon_intensity_series)} countries."
        )

    except requests.exceptions.RequestException as e:
        print(
            f"❌ ERROR: Failed to download the main data file. Please check your internet connection."
        )
        print(f"   Details: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"❌ ERROR: A column name was not found in the CSV: {e}.")
        print("   Please check the column names provided as arguments.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        sys.exit(1)


def main():
    """
    Main function to parse command-line arguments and run the data processing.
    """
    parser = argparse.ArgumentParser(
        description="Fetch OWID energy data, extract the latest carbon intensity for each country, and save it to a pickle file indexed by ISO country code.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_output_filename = "carbon_intensity_data.pkl"
    default_output_path = os.path.join(script_dir, default_output_filename)

    parser.add_argument(
        "--url",
        type=str,
        default="https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv",
        help="URL of the raw CSV data file to process.",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=default_output_path,
        help="File path to save the output pickle file.",
    )
    parser.add_argument(
        "--year-col",
        type=str,
        default="year",
        help="Name of the column containing the year information.",
    )
    parser.add_argument(
        "--value-col",
        type=str,
        default="carbon_intensity_elec",
        help="Name of the column containing the carbon intensity value.",
    )
    parser.add_argument(
        "--country-col",
        type=str,
        default="country",
        help="Name of the column containing the country name.",
    )

    args = parser.parse_args()

    fetch_and_process_latest_carbon_data(
        url=args.url,
        year_col=args.year_col,
        value_col=args.value_col,
        country_col=args.country_col,
        output_path=args.output_path,
    )


if __name__ == "__main__":
    main()
