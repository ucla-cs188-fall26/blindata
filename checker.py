#!/usr/bin/env python3
"""First-pass constraint checker for chart descriptions (CS 188 Core 3).

Loads a chart's data (CSV, TSV, pasted table text, JSON or a Vega-Lite spec),
computes ground-truth facts, then checks a text description against the
constraints in docs/constraints.md. Deterministic and rule-based, stdlib only.

Usage:
    python3 checker.py <data_file> <description_file>
    python3 checker.py            # runs the built-in chart1 examples
"""
import csv, io, json, re, sys
from pathlib import Path

BASE = Path(__file__).parent / "examples"
DEFAULT_UNIT = "units"  # used when the data file carries no axis metadata


# ---------------------------------------------------------------------------
# 1. Data loading: every format ends up as (labels, series, unit)
#    labels: list of category names, e.g. ["Jan", "Feb", ...]
#    series: dict of series name -> list of float values
#    unit:   y-axis unit from the file's metadata, or None if there is none
# ---------------------------------------------------------------------------

def to_number(cell):
    """Turn a cell like '12', '1,234' or 12 into a float."""
    if isinstance(cell, (int, float)):
        return float(cell)
    return float(str(cell).strip().replace(",", ""))

def is_number(cell):
    try:
        to_number(cell)
        return True
    except (TypeError, ValueError):
        return False

def from_table(rows):
    """rows = list of lists; first row is the header, first column is the labels."""
    rows = [r for r in rows if any(c.strip() for c in r)]
    header = [h.strip() for h in rows[0]]
    labels = [r[0].strip() for r in rows[1:]]
    series = {name: [to_number(r[i]) for r in rows[1:]]
              for i, name in enumerate(header) if i > 0}
    return labels, series, None

def from_row_objects(rows, label_key=None):
    """rows = [{"month": "Jan", "apples": 10, ...}, ...]."""
    keys = list(rows[0])
    if label_key is None:  # first column that is not a number
        label_key = next((k for k in keys if not is_number(rows[0][k])), keys[0])
    labels = [str(r[label_key]) for r in rows]
    series = {k: [to_number(r[k]) for r in rows]
              for k in keys if k != label_key and is_number(rows[0][k])}
    return labels, series, None

def from_vega_lite(spec):
    """Read data.values; use the x / y / color fields from the encoding if present."""
    values = spec["data"]["values"]
    enc = spec.get("encoding", {})
    x = enc.get("x", {}).get("field")
    y = enc.get("y", {}).get("field")
    color = enc.get("color", {}).get("field")
    y_enc = enc.get("y", {})
    unit = y_enc.get("title") or (y_enc.get("axis") or {}).get("title")

    if x and y and color:
        # long format: one row per (label, series) pair -> pivot it
        labels, by_series = [], {}
        for row in values:
            label, name = str(row[x]), str(row[color])
            if label not in labels:
                labels.append(label)
            by_series.setdefault(name, {})[label] = to_number(row[y])
        series = {name: [d[l] for l in labels] for name, d in by_series.items()}
    elif x and y:
        labels = [str(row[x]) for row in values]
        series = {y: [to_number(row[y]) for row in values]}
    else:
        labels, series, _ = from_row_objects(values, label_key=x)
    return labels, series, unit

def from_json(obj):
    if isinstance(obj, list):                               # list of row objects
        return from_row_objects(obj)
    if isinstance(obj, dict) and "labels" in obj and "series" in obj:
        unit = obj.get("unit") or obj.get("y_title")
        series = {k: [to_number(v) for v in vals] for k, vals in obj["series"].items()}
        return [str(l) for l in obj["labels"]], series, unit
    if isinstance(obj, dict) and isinstance(obj.get("data"), dict) and "values" in obj["data"]:
        return from_vega_lite(obj)
    raise ValueError("unrecognized JSON shape: expected {labels, series}, "
                     "a list of row objects, or a Vega-Lite spec")

def from_pasted_text(text):
    """A table copied from Excel / Google Sheets: tab-separated or whitespace-aligned."""
    lines = [l for l in text.splitlines() if l.strip()]
    if any("\t" in l for l in lines):
        return from_table([l.split("\t") for l in lines])
    # whitespace-aligned: columns are separated by 2+ spaces, so a label like
    # "New York" survives; fall back to any whitespace if that doesn't line up
    rows = [re.split(r"\s{2,}", l.strip()) for l in lines]
    if len(rows[0]) < 2 or any(len(r) != len(rows[0]) for r in rows):
        rows = [l.split() for l in lines]
    return from_table(rows)

def sniff(text):
    """Guess the format of a .txt (or unknown) file from its content."""
    start = text.lstrip()[:1]
    if start in ("{", "["):
        return from_json(json.loads(text))
    first = text.lstrip().splitlines()[0]
    if "\t" not in first and "," in first and "  " not in first:
        return from_table(list(csv.reader(io.StringIO(text))))
    return from_pasted_text(text)

def load(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")  # -sig strips an Excel BOM
    ext = path.suffix.lower()
    if ext == ".csv":
        labels, series, unit = from_table(list(csv.reader(io.StringIO(text))))
    elif ext == ".tsv":
        labels, series, unit = from_table(list(csv.reader(io.StringIO(text), delimiter="\t")))
    elif ext == ".json":
        labels, series, unit = from_json(json.loads(text))
    else:  # .txt or anything else: look at the content
        labels, series, unit = sniff(text)
    # normalize: the checks match lowercase series names against lowercase text
    series = {name.strip().lower(): vals for name, vals in series.items()}
    unit = unit.strip().lower() if unit else None
    return [l.strip() for l in labels], series, unit


# ---------------------------------------------------------------------------
# 2. Ground-truth facts and the checks
# ---------------------------------------------------------------------------

def facts(labels, series):
    out = {}
    for name, vals in series.items():
        trend = "rises" if vals[-1] > vals[0] else "falls" if vals[-1] < vals[0] else "flat"
        mx = max(vals); mn = min(vals)
        out[name] = dict(start=vals[0], end=vals[-1], trend=trend,
                         max=(mx, labels[vals.index(mx)]),
                         min=(mn, labels[vals.index(mn)]),
                         values=set(vals))
    return out

SAY_TREND = {"rises": "go up", "falls": "go down", "flat": "stay flat"}

UNIT_WORDS = ["kilogram", "gram", "pound", "ton", "liter", "litre",
              "dollar", "euro", "percent", "unit"]

# Claims the data alone cannot decide. Checked sentence by sentence.
UNVERIFIABLE_CUES = {
    "a causal claim": [r"\bcaused?\b", r"\bcauses\b", r"\bled to\b", r"\bleads? to\b",
                       r"\bbecause\b", r"\bdue to\b", r"\bresult(?:ed|s)? in\b",
                       r"\bas a result\b", r"\bthanks to\b", r"\bdriven by\b"],
    "a prediction": [r"\bwill\b", r"\b(?:is|are) expected to\b", r"\blikely to\b",
                     r"\bgoing to\b", r"\bforecast\w*\b", r"\bpredict\w*\b"],
    "an opinion or judgment": [r"\bimpressive\w*\b", r"\bdramatic\w*\b", r"\bremarkabl\w*\b",
                               r"\bsignificant\w*\b", r"\bdisappointing\w*\b",
                               r"\bsurprising\w*\b", r"\bamazing\w*\b", r"\bstunning\w*\b",
                               r"\bexcellent\b", r"\bpoor\b", r"\bworrying\b"],
}

def find_cue(sentence):
    """Return (kind, matched words) for the first cue found, or None."""
    for kind, patterns in UNVERIFIABLE_CUES.items():
        for p in patterns:
            m = re.search(p, sentence)
            if m:
                return kind, m.group(0)
    return None

def check(text, labels, series, f, unit):
    low = text.lower()
    verified, contradicted, unverifiable, missing = [], [], [], []

    # 4. units: compare unit words in the description with the chart's unit
    chart_units = [w for w in UNIT_WORDS if re.search(r"\b" + w, unit)]
    if chart_units:
        for w in UNIT_WORDS:
            m = re.search(r"\b" + w + r"s?\b", low)
            if not m:
                continue
            if w in chart_units:
                verified.append(f"Units: the description says {m.group(0)}, "
                                f"which matches the chart unit, {unit}.")
            else:
                contradicted.append(f"Units: the description says {m.group(0)}, "
                                    f"but the chart unit is {unit}.")

    # 2. trend claims like "apples rise/fall ..."
    for name in series:
        m = re.search(name + r"\s+(rise|rises|rose|fall|falls|fell|increase|increases|decrease|decreases)", low)
        if m:
            claimed = "rises" if m.group(1).startswith(("rise", "rose", "increase")) else "falls"
            real = f[name]["trend"]
            if claimed != real:
                contradicted.append(
                    f"Trend: the description says {name} {SAY_TREND[claimed]}, but in the data "
                    f"they {SAY_TREND[real]}, from {f[name]['start']:g} to {f[name]['end']:g}.")
            else:
                verified.append(f"Trend: {name} {SAY_TREND[claimed]} overall, which matches the data.")

    # 1. numbers must exist in the data (each distinct number reported once)
    allvals = set().union(*[s["values"] for s in f.values()])
    seen = []
    for num in re.findall(r"\d+(?:\.\d+)?", text):
        if num in seen:
            continue
        seen.append(num)
        if float(num) in allvals:
            verified.append(f"Values: the number {num} appears in the data.")
        else:
            contradicted.append(f"Values: the number {num} does not appear anywhere in the data.")

    # 3. peak claims, tied to the series named in the same sentence
    MONTHS = ["january", "february", "march", "april", "may", "june", "july",
              "august", "september", "october", "november", "december"]
    ABBR = {full: full[:3].capitalize() for full in MONTHS}
    for sent in re.split(r"[.!\n]", low):
        pm = re.search(r"peak\w*\s+in\s+(\w+)", sent)
        if not pm:
            continue
        month = ABBR.get(pm.group(1), pm.group(1).capitalize())
        for name in series:
            if name in sent:
                real_month, real_val = f[name]["max"][1], f[name]["max"][0]
                if month != real_month:
                    contradicted.append(f"Peak: the description puts the {name} peak in {month}, "
                                        f"but the real maximum is {real_val:g} in {real_month}.")
                else:
                    verified.append(f"Peak: {name} peak in {month}, which matches the data.")

    # Unverifiable: causal claims, predictions, opinions. Not errors, just
    # things a data table cannot confirm or deny.
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        sent = sent.strip()
        if not sent:
            continue
        cue = find_cue(sent.lower())
        if cue:
            kind, word = cue
            unverifiable.append(f'The sentence "{sent}" is {kind} (it says "{word}"). '
                                f"The data alone cannot confirm or deny it.")

    # 5. completeness: every series mentioned?
    for name in series:
        if name not in low:
            missing.append(f"The series {name} is in the data but is never mentioned.")

    return dict(verified=verified, contradicted=contradicted,
                unverifiable=unverifiable, missing=missing)


# ---------------------------------------------------------------------------
# 3. Report: plain sentences, summary first, so it reads well aloud
# ---------------------------------------------------------------------------

def plural(n, word, many=None):
    return f"{n} {word}" if n == 1 else f"{n} {many or word + 's'}"

def report(title, b):
    v, c, u, m = (len(b[k]) for k in ("verified", "contradicted", "unverifiable", "missing"))
    lines = [f"Report for {title}.",
             f"Summary: {plural(v + c + u, 'claim')} checked: {v} verified, {c} contradicted, "
             f"{u} unverifiable, {plural(m, 'missing item')}."]
    groups = [("verified", "Verified claims, these agree with the data"),
              ("contradicted", "Contradicted claims, these disagree with the data"),
              ("unverifiable", "Unverifiable claims, the data cannot decide these"),
              ("missing", "Missing items, these are in the data but not in the description")]
    for key, heading in groups:
        if b[key]:
            lines.append(f"{heading}: {len(b[key])}.")
            lines += b[key]
    return "\n".join(lines)

def run(data_file, description_file):
    labels, series, unit = load(data_file)
    f = facts(labels, series)
    text = Path(description_file).read_text(encoding="utf-8")
    buckets = check(text, labels, series, f, unit or DEFAULT_UNIT)
    print(report(Path(description_file).name, buckets))

def main():
    args = sys.argv[1:]
    if len(args) == 2:
        run(args[0], args[1])
    elif not args:  # old default: the built-in examples
        for fn in ["chart1_description_correct.txt", "chart1_description_wrong.txt"]:
            run(BASE / "chart1_data.csv", BASE / fn)
            print()
    else:
        print("usage: python3 checker.py <data_file> <description_file>", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
