# FDIC 2025Q4 Assignment: Execution Guide

The submission script is `20206449_FDIC_2025Q4.py`. The original household-sector example files have not been modified.
The Python script and its outputs are complete; the PowerPoint presentation must be prepared separately.

## Steps to complete manually

1. Upload the Python file through the file panel in Google Colab. Run the following command in a runtime with internet access. If you rename the file, use the same filename in the command.

   ```python
   %run 20206449_FDIC_2025Q4.py
   ```

   The assignment's `%run fdic_2025q4_balance_sheet.py` is an example. The filename after `%run` must match the file you actually uploaded.

2. Check the console for `[PASS]` and the saved-file messages, then download the outputs from Colab's file panel before the runtime ends.
3. Prepare approximately 20 PowerPoint slides covering the program flow, key syntax and commands, results, and interpretation. Be ready to explain the code yourself. Submit the `.py` file with your student ID and the `.pptx` file through eClass. No eClass submission has been performed as part of this work.

No API key, `pip install`, input CSV, or configuration change is required. The script was executed successfully against the live FDIC API using Python 3.10 in this environment. It has not been run within Google Colab itself.

## Generated files

| File | Contents |
|---|---|
| `fdic_2025q4_institution_financials.csv` | Institution identifiers, original API accounts, calculated accounts, and institution-level balance differences. All monetary values are in USD thousands. |
| `fdic_2025q4_aggregate_balance_sheet.csv` | Aggregate accounts, amounts in USD thousands and billions, shares of total assets, calculation methods, and source fields or formulas. |
| `fdic_2025q4_run_metadata.json` | Additional reproducibility information: retrieval timestamps, actual request URLs, API version, institution counts by class, and the balance difference. |

Outputs are saved to the current working directory. Rerunning the script replaces files with the same names. The aggregate CSV contains both totals and components; summing every row would double-count amounts. Use `row_type` to distinguish them.

## Key design choices to explain

- **Historical population:** Query `financials` using `REPDTE:20251231`, `INSDIF:1`, and `BKCLASS:(N OR NM OR SM OR SB OR SI OR SL)` together. Uninsured institutions and U.S. branches of foreign banks are excluded. The historical sample is not restricted using today's operating status.
- **Complete retrieval:** Sort by CERT and retrieve 1,000 records per page until all `meta.total` records have been collected. Stop if the API data version or total count changes during retrieval.
- **Validation:** Check required fields, missing values, dates, institution classes, duplicate CERTs, and institution-level and aggregate accounting identities. Missing values are never silently replaced with zero.
- **Total equity:** Use the official total equity field `EQTOT`. Some institutions report different values for `EQ`, so checking `ASSET = LIAB + EQ` would not balance. Retain `EQ` in the CSV for comparison. Do not derive equity as assets minus liabilities merely to make the validation pass.
- **Borrowed funds:** Define this category as `FREPP + OTHBRF + SUBND`: federal funds and repo borrowing, other borrowed funds, and subordinated debt. Both the CSV and console explicitly state that subordinated debt is included. `BRO` denotes brokered deposits and is not used as the borrowed-funds field.
- **Other accounts:** Summary other assets equal `ASSET - CHBAL - SC - LNLSNET`; summary other liabilities equal `LIAB - DEP - FREPP - OTHBRF - SUBND`. Both are labeled **calculated residual**. The API's `OA` and `ALLOTHL` are narrower detailed accounts. For example, the summary asset residual also includes trading assets and fixed assets, while the liability residual includes trading liabilities. Preserve both API fields in the institution data, but do not equate them with the broader residuals or add them again.
- **Units:** Convert USD thousands to USD billions by **dividing by 1,000,000**. Validate the original integer amounts before rounding. Display three decimal places in the console and preserve six decimal places in the CSV billions column to retain the original precision.
- **Additional analysis:** Calculate funding shares, the five largest institutions' share of total assets, and the distribution of institutions with assets below USD 1 billion, from USD 1 billion to below USD 10 billion, and at least USD 10 billion. The standard-library implementation also differs from the example's pandas-based time-series selection structure.

The main workflow is `retrieve_all → validate_and_enrich → aggregate → print_analysis → write_csv`. Key syntax includes functions, `while`/`for`, dictionaries, list comprehensions, `sum`, `sorted`, `try/except`, `with`, and `if __name__ == "__main__"`.

## Verified results and review points

These results were retrieved on September 21, 2026. Amounts are in USD billions. Rerunning the program may produce different results if the API data are revised.

| Account | Amount |
|---|---:|
| Total assets | 25,257.206 |
| Cash and balances due | 2,572.471 |
| Securities | 5,712.108 |
| Net loans and leases | 13,255.133 |
| Other assets — calculated residual | 3,717.495 |
| Deposits | 20,077.278 |
| Borrowed funds — including subordinated debt | 1,645.723 |
| Other liabilities — calculated residual | 935.613 |
| Total liabilities | 22,658.614 |
| Total equity capital | 2,598.592 |

Before rounding, in USD thousands, **25,257,205,993 = 22,658,613,881 + 2,598,592,112**, with a difference of zero. The accounting identity also holds for all 4,338 individual institutions. Checks confirmed that the program rejects missing values, duplicate institutions, incorrect report dates, and equity discrepancies, and handles a partially filled final page correctly.

**Review before preparing the slides:** The FDIC's initial 2025Q4 release reported 4,336 institutions, whereas this API query returned 4,338 under the stated filters. This aggregation uses the institution-level observations returned by the API. The specific reasons for the discrepancy have not been established, so do not attribute it solely to revisions. State the retrieval date and selection criteria in the presentation. If the course requires an exact match to the initial release, confirm the required data vintage and population with the instructor. Do not arbitrarily delete two institutions or alter totals to force a match.

Deposits represent 79.49% of total assets, book total equity represents 10.29%, and the five largest institutions hold 42.46% of total assets. These figures provide a starting point for discussing deposit-based funding and asset concentration among large institutions. Book equity ratios differ from regulatory capital ratios such as CET1. Summing institution balance sheets does not produce a consolidated balance sheet with interbank positions eliminated. A single quarter cannot establish changes in risk or determine overall financial soundness.

## Official references

- [FDIC BankFind Suite API documentation](https://api.fdic.gov/banks/docs/)
- [Financial variable and institution classification definitions](https://api.fdic.gov/banks/docs/risview_properties.yaml)
- [BankFind financial reporting interface — monetary units](https://banks.data.fdic.gov/bankfind-suite/financialreporting/report)
- [FDIC 2025Q4 Quarterly Banking Profile](https://www.fdic.gov/quarterly-banking-profile/quarterly-banking-profile-q4-2025)
- [Initial release — 4,336 institutions](https://content.govdelivery.com/accounts/USFDIC/bulletins/40b2c3e)
