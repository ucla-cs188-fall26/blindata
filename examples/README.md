# Test examples

chart1: fruit sales, two series (apples, oranges), Jan-Jun, unit "units".

The same data in every supported input format (all give identical reports):

- `chart1_data.csv` - CSV
- `chart1_data.tsv` - TSV
- `chart1_data_pasted_tabs.txt` - table pasted from Excel/Sheets (tab-separated)
- `chart1_data_pasted_aligned.txt` - whitespace-aligned pasted table
- `chart1_data_labels.json` - JSON `{"labels": [...], "series": {...}, "unit": ...}`
- `chart1_data_rows.json` - JSON list of row objects
- `chart1_vegalite.json` - Vega-Lite spec (long format, x/y/color encoding, y-axis title)

Descriptions:

- `chart1_description_correct.txt` - every claim agrees with the data.
  Expected: no details conflict with the data and nothing is potentially
  missing. Numeric mentions are reported separately because the generic number
  check does not verify their series/category context.
- `chart1_description_wrong.txt` - planted errors:
  - wrong units (kilograms, data is units sold) -> conflicts with data
  - trend reversed (says apples fall, they rise) -> conflicts with data
  - wrong peak (says February 14, real peak is June 27) -> conflicts with data
  - number 20 does not appear among the data values, but this generic check
    cannot determine whether its use is incorrect without claim context
  - causal claim ("because of the new marketing campaign") -> cannot be assessed from data
  - values swapped (27 was June, not January): NOT caught yet; the generic
    number check does not associate values with their claimed categories

Run one pair: `python3 checker.py examples/chart1_vegalite.json examples/chart1_description_wrong.txt`
