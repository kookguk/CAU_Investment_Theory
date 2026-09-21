"""Construct the U.S. household-sector balance sheet for 2026:Q1.

Source: Board of Governors of the Federal Reserve System,
Financial Accounts of the United States (Z.1), Household Balance Sheet.

The official sector is "Households and nonprofit organizations." The Federal
Reserve reports the selected series in millions of current U.S. dollars. This
program converts them to billions of dollars for display and CSV output.
"""

from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pandas as pd


DATA_URL = (
    "https://www.federalreserve.gov/releases/z1/dataviz/download/"
    "zips/z1-visualization.zip"
)
CSV_NAME = "z1-visualization-data.csv"
TARGET_QUARTER = "2026:Q1"
OUTPUT_DIR = Path("us_household_balance_sheet_2026q1_output")


SERIES = {
    "Net worth": "FL152090005.Q",
    "Total assets": "FL152000005.Q",
    "Nonfinancial assets": "LM152010005.Q",
    "Real estate": "LM155035015.Q",
    "Consumer durables": "LM155111005.Q",
    "Nonprofit organizations' nonfinancial assets": "LM162010005.Q",
    "Financial assets": "FL154090005.Q",
    "Deposits": "FL154000025.Q",
    "Directly held corporate equities": "LM153064105.Q",
    "Indirectly held corporate equities": "LM153064175.Q",
    "Directly held debt securities": "LM154022005.Q",
    "Indirectly held debt securities": "LM154022075.Q",
    "Defined benefit pension entitlements": "FL594190045.Q",
    "Equity in noncorporate businesses": "LM152090205.Q",
    "Other financial assets": "FL153099005.Q",
    "Total liabilities": "FL154190005.Q",
    "Home mortgages": "FL153165105.Q",
    "Consumer credit": "FL153166000.Q",
    "Other liabilities": "FL154199005.Q",
}


def download_z1_data() -> pd.DataFrame:
    """Download the official Z.1 ZIP file and read its CSV into a DataFrame."""
    request = Request(DATA_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=120) as response:
        zip_bytes = response.read()

    with ZipFile(BytesIO(zip_bytes)) as archive:
        if CSV_NAME not in archive.namelist():
            raise RuntimeError(f"{CSV_NAME} was not found in the downloaded ZIP file.")
        with archive.open(CSV_NAME) as csv_file:
            return pd.read_csv(csv_file)


def construct_balance_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    """Select 2026:Q1, translate series codes, and convert units."""
    missing_series = [code for code in SERIES.values() if code not in raw.columns]
    if missing_series:
        raise RuntimeError(f"Federal Reserve series missing: {missing_series}")

    selected = raw.loc[raw["date"] == TARGET_QUARTER]
    if len(selected) != 1:
        raise RuntimeError(
            f"Expected one observation for {TARGET_QUARTER}, found {len(selected)}."
        )

    observation = selected.iloc[0]
    balance_sheet = pd.DataFrame(
        {
            "Series code": SERIES,
            "Amount ($ millions)": {
                account: observation[code] for account, code in SERIES.items()
            },
        }
    )
    balance_sheet.index.name = "Account"
    balance_sheet["Amount ($ billions)"] = balance_sheet["Amount ($ millions)"] / 1_000
    balance_sheet["Share of total assets (%)"] = (
        balance_sheet["Amount ($ millions)"]
        / balance_sheet.loc["Total assets", "Amount ($ millions)"]
        * 100
    )
    return balance_sheet


def validate_balance_sheet(balance_sheet: pd.DataFrame) -> None:
    """Verify the principal asset and net-worth identities."""
    amount = balance_sheet["Amount ($ millions)"]

    asset_subtotal_difference = (
        amount["Total assets"]
        - amount["Financial assets"]
        - amount["Nonfinancial assets"]
    )
    net_worth_difference = (
        amount["Total assets"]
        - amount["Total liabilities"]
        - amount["Net worth"]
    )
    liability_detail_difference = (
        amount["Total liabilities"]
        - amount["Home mortgages"]
        - amount["Consumer credit"]
        - amount["Other liabilities"]
    )

    tolerance = 2  # $2 million accommodates rounding in published aggregates.
    checks = {
        "Assets = financial + nonfinancial assets": asset_subtotal_difference,
        "Assets = liabilities + net worth": net_worth_difference,
        "Liabilities = mortgages + consumer credit + other": liability_detail_difference,
    }
    failed = {name: value for name, value in checks.items() if abs(value) > tolerance}
    if failed:
        raise RuntimeError(f"Balance-sheet validation failed: {failed}")

    print("ACCOUNTING CHECKS")
    for name, difference in checks.items():
        print(f"  PASS: {name} (rounding difference = ${difference:,.0f} million)")


def presentation_order(balance_sheet: pd.DataFrame) -> pd.DataFrame:
    """Arrange the accounts in a conventional balance-sheet order."""
    order = [
        "Total assets",
        "Nonfinancial assets",
        "Real estate",
        "Consumer durables",
        "Nonprofit organizations' nonfinancial assets",
        "Financial assets",
        "Deposits",
        "Directly held corporate equities",
        "Indirectly held corporate equities",
        "Directly held debt securities",
        "Indirectly held debt securities",
        "Defined benefit pension entitlements",
        "Equity in noncorporate businesses",
        "Other financial assets",
        "Total liabilities",
        "Home mortgages",
        "Consumer credit",
        "Other liabilities",
        "Net worth",
    ]
    return balance_sheet.loc[order]


def print_interpretation(balance_sheet: pd.DataFrame) -> None:
    """Print a concise interpretation of the 2026:Q1 balance sheet."""
    b = balance_sheet["Amount ($ billions)"]
    share = balance_sheet["Share of total assets (%)"]

    financial_categories = [
        "Deposits",
        "Directly held corporate equities",
        "Indirectly held corporate equities",
        "Directly held debt securities",
        "Indirectly held debt securities",
        "Defined benefit pension entitlements",
        "Equity in noncorporate businesses",
        "Other financial assets",
    ]
    largest = b.loc[financial_categories].sort_values(ascending=False).head(3)

    print("\nINTERPRETATION")
    print(f"Total assets were ${b['Total assets'] / 1_000:,.1f} trillion.")
    print(f"Financial assets represented {share['Financial assets']:.1f}% of total assets.")
    print(f"Nonfinancial assets represented {share['Nonfinancial assets']:.1f}% of total assets.")
    print(f"Net worth represented {share['Net worth']:.1f}% of total assets.")
    print("Largest financial-asset categories:")
    for account, value in largest.items():
        print(f"  {account}: ${value / 1_000:,.1f} trillion")


def main() -> None:
    raw = download_z1_data()
    balance_sheet = construct_balance_sheet(raw)
    validate_balance_sheet(balance_sheet)
    balance_sheet = presentation_order(balance_sheet)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "us_household_balance_sheet_2026q1.csv"
    balance_sheet.round(4).to_csv(output_file)

    print("\nBALANCE SHEET OF U.S. HOUSEHOLDS AND NONPROFIT ORGANIZATIONS")
    print("2026:Q1, amounts in billions of current U.S. dollars\n")
    print(
        balance_sheet[["Amount ($ billions)", "Share of total assets (%)"]]
        .round(3)
        .to_string()
    )
    print_interpretation(balance_sheet)
    print(f"\nCSV file saved as: {output_file.resolve()}")


if __name__ == "__main__":
    main()
