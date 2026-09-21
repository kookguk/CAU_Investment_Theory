"""Aggregate balance sheet of FDIC-insured banks and savings institutions at year-end 2025.

Colab: upload this file and run %run 20206449_FDIC_2025Q4.py
The filename includes the student ID. No code changes are required.
Uses only the Python standard library; no pip installation, API key, or input data file is needed.

Official source and variable definitions:
https://api.fdic.gov/banks/docs/
https://api.fdic.gov/banks/docs/risview_properties.yaml

Original monetary unit: USD thousands. USD billions = USD thousands / 1,000,000.
Institution balance sheets are summed without netting interbank assets and liabilities.
Historical API data may be revised, so the data version is recorded for each run.
"""

import csv
import json
import socket
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.fdic.gov/banks/financials"
REPORT_DATE = "20251231"
PAGE_SIZE = 1000
OUTPUT_DIR = Path.cwd()  # Save to the working directory, usually /content in Colab.
THOUSANDS_PER_BILLION = 1_000_000
CLASSES = ("N", "NM", "SM", "SB", "SI", "SL")
# Filter insurance status and institution class in the historical financials records.
# Today's ACTIVE status could exclude banks merged or closed after the report date.
# Exclude OI (U.S. branches of foreign banks), NC/NS (uninsured), and CU (credit unions).
FILTER = (
    f"REPDTE:{REPORT_DATE} AND INSDIF:1 "
    f"AND BKCLASS:({' OR '.join(CLASSES)})"
)
IDENTIFIERS = ("CERT", "NAME", "REPDTE", "BKCLASS", "INSDIF")
MONEY_FIELDS = (
    "ASSET", "CHBAL", "SC", "LNLSNET", "DEP", "FREPP", "OTHBRF",
    "SUBND", "LIAB", "EQTOT", "EQ", "OA", "ALLOTHL",
)
FIELDS = IDENTIFIERS + MONEY_FIELDS

# Define display accounts, source/calculated fields, methods, and formulas.
# Distinguish totals from their component accounts.
ACCOUNTS = (
    ("Assets", "component", "Cash and balances due", "CHBAL", "reported", "CHBAL"),
    ("Assets", "component", "Securities", "SC", "reported", "SC"),
    ("Assets", "component", "Net loans and leases", "LNLSNET", "reported", "LNLSNET"),
    ("Assets", "component", "Other assets (calculated residual)",
     "OTHER_ASSETS_CALC", "calculated", "ASSET - CHBAL - SC - LNLSNET"),
    ("Assets", "total", "Total assets", "ASSET", "reported", "ASSET"),
    ("Liabilities", "component", "Deposits", "DEP", "reported", "DEP"),
    ("Liabilities", "component", "Borrowed funds (including subordinated debt)",
     "BORROWED_FUNDS_CALC", "calculated", "FREPP + OTHBRF + SUBND"),
    ("Liabilities", "component", "Other liabilities (calculated residual)",
     "OTHER_LIABILITIES_CALC", "calculated", "LIAB - DEP - FREPP - OTHBRF - SUBND"),
    ("Liabilities", "total", "Total liabilities", "LIAB", "reported", "LIAB"),
    ("Equity", "total", "Total equity capital", "EQTOT", "reported", "EQTOT"),
)
DERIVED_FIELDS = (
    "BORROWED_FUNDS_CALC", "OTHER_ASSETS_CALC", "OTHER_LIABILITIES_CALC",
    "BALANCE_DIFFERENCE_CALC",
)


def fetch_page(offset):
    """Retrieve one page with GET and retry only transient network errors."""
    params = {
        "filters": FILTER, "fields": ",".join(FIELDS), "format": "json",
        "sort_by": "CERT", "sort_order": "ASC", "limit": PAGE_SIZE,
        "offset": offset,
    }
    url = API_URL + "?" + urlencode(params)
    request = Request(url, headers={"Accept": "application/json",
                                    "User-Agent": "FDIC-Balance-Sheet-Student-Project/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                # Parse decimal values without introducing binary floating-point errors.
                return json.load(response, parse_float=Decimal), url
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f"FDIC HTTP error {exc.code}: {url}") from exc
        except (URLError, TimeoutError, socket.timeout) as exc:
            if attempt == 2:
                raise RuntimeError("FDIC connection failed. Check your internet connection and rerun.") from exc
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError("The FDIC response is not valid JSON.") from exc
        print(f"  Temporary connection error: retrying in {2 ** (attempt + 1)} seconds")
        time.sleep(2 ** (attempt + 1))


def retrieve_all():
    """Fetch all meta.total records to avoid truncation by the API's default page limit."""
    records, urls = [], []
    expected_total, first_index = None, None
    while expected_total is None or len(records) < expected_total:
        payload, url = fetch_page(len(records))
        try:
            total = payload["meta"]["total"]
            index = payload["meta"].get("index", {})
            page = [entry["data"] for entry in payload["data"]]
        except (KeyError, TypeError) as exc:
            raise RuntimeError("The FDIC response has an unexpected structure.") from exc
        if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
            raise ValueError(f"No valid target institutions: meta.total={total!r}")
        if expected_total is None:
            expected_total, first_index = total, index
        if total != expected_total or index != first_index:
            raise ValueError("The API data version or institution count changed during retrieval. Rerun.")
        if not page or len(records) + len(page) > expected_total:
            raise ValueError("An API page is empty or the returned record count exceeds the total.")
        records.extend(page)
        urls.append(url)
        print(f"  Downloaded: {len(records):,} / {expected_total:,} institutions")
    return records, {"api_total": expected_total, "api_index": first_index,
                     "request_urls": urls}


def exact_integer(value, field, cert):
    """Reject missing values rather than replacing them with zero; require integer values."""
    try:
        if value is None or isinstance(value, bool):
            raise ValueError
        number = Decimal(str(value))
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"CERT={cert}: {field} is missing or invalid: {value!r}") from exc


def validate_and_enrich(records):
    """Validate institutions, dates, and values, then calculate summary accounts and balance differences."""
    cleaned, seen = [], set()
    for record in records:
        missing = [field for field in FIELDS if field not in record]
        if missing:
            raise ValueError(f"CERT={record.get('CERT')}: missing fields {missing}")
        row = {field: record[field] for field in FIELDS}
        cert = exact_integer(row["CERT"], "CERT", row["CERT"])
        row["CERT"] = cert
        if cert <= 0 or cert in seen:
            raise ValueError(f"Invalid or duplicate CERT: {cert}")
        seen.add(cert)
        if str(row["REPDTE"]) != REPORT_DATE:
            raise ValueError(f"CERT={cert}: unexpected report date.")
        if row["BKCLASS"] not in CLASSES or str(row["INSDIF"]) != "1":
            raise ValueError(f"CERT={cert}: institution is outside the target population.")
        if not isinstance(row["NAME"], str) or not row["NAME"].strip():
            raise ValueError(f"CERT={cert}: institution name is missing.")
        for field in MONEY_FIELDS:
            row[field] = exact_integer(row[field], field, cert)
        if row["ASSET"] <= 0:
            raise ValueError(f"CERT={cert}: total assets must be positive.")

        # Borrowed funds: federal funds/repo borrowing + other borrowing + subordinated debt.
        row["BORROWED_FUNDS_CALC"] = row["FREPP"] + row["OTHBRF"] + row["SUBND"]
        # Residuals cover all omitted summary accounts, unlike the narrower API OA/ALLOTHL fields.
        row["OTHER_ASSETS_CALC"] = row["ASSET"] - row["CHBAL"] - row["SC"] - row["LNLSNET"]
        row["OTHER_LIABILITIES_CALC"] = row["LIAB"] - row["DEP"] - row["BORROWED_FUNDS_CALC"]
        # Verify using independently reported EQTOT, not equity derived as assets minus liabilities.
        row["BALANCE_DIFFERENCE_CALC"] = row["ASSET"] - row["LIAB"] - row["EQTOT"]
        if row["BALANCE_DIFFERENCE_CALC"] != 0:
            raise ValueError(f"CERT={cert}: assets-liabilities-total equity={row['BALANCE_DIFFERENCE_CALC']:,} USD thousands")
        if row["OTHER_ASSETS_CALC"] < 0 or row["OTHER_LIABILITIES_CALC"] < 0:
            raise ValueError(f"CERT={cert}: negative residual. Check the account definitions.")
        cleaned.append(row)
    if not cleaned:
        raise ValueError("No institutions are available for aggregation.")
    return sorted(cleaned, key=lambda row: row["CERT"])


def aggregate(records):
    """Sum Python integers and preserve six decimal places in the CSV billions column."""
    totals = {field: sum(row[field] for row in records)
              for field in MONEY_FIELDS + DERIVED_FIELDS}
    difference = totals["ASSET"] - totals["LIAB"] - totals["EQTOT"]
    if difference != 0:
        raise ValueError(f"Industry accounting identity does not balance: {difference}")
    rows = []
    for side, kind, account, field, method, formula in ACCOUNTS:
        amount = totals[field]
        rows.append({
            "report_date": "2025-12-31", "side": side, "row_type": kind,
            "account": account, "amount_usd_thousands": amount,
            "amount_usd_billions": format(Decimal(amount) / THOUSANDS_PER_BILLION, ".6f"),
            "share_of_total_assets_pct": f"{amount / totals['ASSET'] * 100:.6f}",
            "method": method, "source_or_formula": formula,
            "institution_count": len(records),
        })
    # Residual subtotals verify presentation logic, not an independent economic identity.
    for side, total_field in (("Assets", "ASSET"), ("Liabilities", "LIAB")):
        subtotal = sum(row["amount_usd_thousands"] for row in rows
                       if row["side"] == side and row["row_type"] == "component")
        if subtotal != totals[total_field]:
            raise ValueError(f"{side} displayed components do not match the total.")
    return rows, totals


def print_analysis(records, rows, totals):
    """Supplement aggregate amounts with funding structure and asset concentration analysis."""
    print("\nFDIC-INSURED COMMERCIAL BANKS AND SAVINGS INSTITUTIONS | 2025-12-31")
    print(f"Institutions: {len(records):,} | Amounts: USD billions\n")
    for row in rows:
        print(f"{row['account']:<52} {float(row['amount_usd_billions']):>14,.3f}")
    print("\nValidation: ASSET = LIAB + EQTOT for every institution and the industry [PASS]")
    print("Industry balance difference: 0 USD thousands (exact integers before rounding)")
    ratio = lambda numerator, denominator: 100 * numerator / denominator
    print("\n[Additional analysis: funding structure and asset concentration]")
    for label, field in (("Deposits / total assets", "DEP"), ("Borrowed funds / total assets", "BORROWED_FUNDS_CALC"),
                         ("Book total equity / total assets", "EQTOT"), ("Net loans / total assets", "LNLSNET")):
        print(f"{label}: {ratio(totals[field], totals['ASSET']):.2f}%")
    if totals["DEP"] > 0:
        print(f"Net loans / deposits: {ratio(totals['LNLSNET'], totals['DEP']):.2f}%")
    leaders = sorted(records, key=lambda row: (-row["ASSET"], row["CERT"]))[:5]
    concentration = ratio(sum(row["ASSET"] for row in leaders), totals["ASSET"])
    print(f"Top five institutions' share of total assets: {concentration:.2f}%")
    for row in leaders:
        print(f"  {row['CERT']:>6}  {row['NAME']:<42} {row['ASSET'] / THOUSANDS_PER_BILLION:>12,.3f}")
    print("\nDistribution by institution size (total assets, USD billions)")
    for label, low, high in (("< 1", 0, 1_000_000),
                             ("1 to < 10", 1_000_000, 10_000_000),
                             (">= 10", 10_000_000, float('inf'))):
        group = [row for row in records if low <= row["ASSET"] < high]
        assets = sum(row["ASSET"] for row in group)
        print(f"  {label:<12}: {len(group):>4} institutions, asset share {ratio(assets, totals['ASSET']):6.2f}%")
    print("\nInterpretation: deposit and borrowing shares describe funding; the top-five share measures asset concentration.")
    print("Book equity ratios differ from regulatory capital ratios such as CET1. A single date cannot establish soundness trends.")
    print("Interbank positions are not netted. Institution-level concentration also differs from holding-company concentration.")
    print("Deposits include foreign-office deposits; the total does not imply that every deposit dollar is insured.")
    print("Reported OA/ALLOTHL are retained in the institution data and differ from the broad summary residuals.")


def write_csv(path, rows, columns):
    """Write UTF-8 with a BOM so Excel can recognize the text encoding."""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    started = datetime.now(timezone.utc).isoformat()
    print(f"FDIC API retrieval started (UTC): {started}\nFilter: {FILTER}")
    raw, metadata = retrieve_all()
    records = validate_and_enrich(raw)
    if len(records) != metadata["api_total"]:
        raise ValueError("The institution count does not match the API total.")
    rows, totals = aggregate(records)
    print_analysis(records, rows, totals)

    # Save only after all checks pass. Rerunning replaces outputs with the same filenames.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    institution_path = OUTPUT_DIR / "fdic_2025q4_institution_financials.csv"
    aggregate_path = OUTPUT_DIR / "fdic_2025q4_aggregate_balance_sheet.csv"
    write_csv(institution_path, records, FIELDS + DERIVED_FIELDS)
    write_csv(aggregate_path, rows, list(rows[0]))
    metadata.update({
        "retrieval_started_utc": started,
        "retrieval_completed_utc": datetime.now(timezone.utc).isoformat(),
        "report_date": REPORT_DATE, "source": API_URL, "filter": FILTER,
        "raw_monetary_unit": "USD thousands", "billions_divisor": THOUSANDS_PER_BILLION,
        "institution_count": len(records),
        "class_counts": dict(Counter(row["BKCLASS"] for row in records)),
        "balance_difference_usd_thousands": totals["BALANCE_DIFFERENCE_CALC"],
        "borrowed_funds_definition": "FREPP + OTHBRF + SUBND",
        "aggregation_scope": "Sum of institution balance sheets; interbank positions not netted",
        "residual_note": "Broad presentation residuals differ from reported OA and ALLOTHL",
    })
    metadata_path = OUTPUT_DIR / "fdic_2025q4_run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    for path in (institution_path, aggregate_path, metadata_path):
        print(f"Saved: {path.resolve()}")


if __name__ == "__main__":
    main()
