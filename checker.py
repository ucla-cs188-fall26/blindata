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

MONTH_NAMES = ("january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december")
MONTH_ALIASES = {alias: full for full in MONTH_NAMES
                 for alias in (full, full[:3])}
MONTH_ALIASES["sept"] = "september"
NUMBER = r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w|\.\d)"
MAX_CUE = r"\b(?:peaks?|peaked|peaking|max|maximum|maxima|highest|largest|greatest|biggest|high point|record high|all-time high|top value|(?:reach(?:es|ed)?|hits?|hit) (?:a |its |the )?high)\b"
MIN_CUE = r"\b(?:min|minimum|minima|lowest|smallest|fewest|troughs?|bottoms?(?:ed)? out|low point|record low|all-time low|(?:reach(?:es|ed)?|hits?|hit) (?:a |its |the )?low)\b"
TREND_CUES = {
    "rises": r"\b(?:ris(?:e[sd]?|ing)|rose|increas(?:e[sd]?|ing)|grow[sn]?|grew|growing|climb(?:s|ed|ing)?|went up|go(?:es|ing)? up|upward(?:s)?|uptrend)\b",
    "falls": r"\b(?:falls?|fell|fallen|falling|decreas(?:e[sd]?|ing)|declin(?:e[sd]?|ing)|drop(?:s|ped|ping)?|dip(?:s|ped|ping)?|shrink(?:s|ing)?|shrank|shrunk|went down|go(?:es|ing)? down|downward(?:s)?|downtrend)\b",
    "flat": r"\b(?:flat|stable|constant|unchanged|steady|no change|did not change|does not change|do not change|remain(?:s|ed)? (?:the same|level))\b",
}


def word_pattern(value):
    return r"(?<!\w)" + re.escape(value) + r"(?!\w)"


def label_mentions(text, labels):
    """Resolve actual categories, including full/abbreviated month spellings."""
    found = []
    for index, label in enumerate(labels):
        canonical = MONTH_ALIASES.get(label.lower().rstrip('.'))
        aliases = {label.lower()}
        if canonical:
            aliases.update(a for a, full in MONTH_ALIASES.items() if full == canonical)
        for alias in aliases:
            for match in re.finditer(word_pattern(alias), text):
                found.append((match.start(), match.end(), index))
    return sorted(set(found))


def claim_clauses(text, labels, series):
    """Keep series-specific clauses apart; inherit a subject only within a sentence."""
    names = '|'.join(re.escape(n) for n in sorted(series, key=len, reverse=True))
    aliases = set(l.lower() for l in labels) | set(MONTH_ALIASES)
    categories = '|'.join(re.escape(l) for l in sorted(aliases, key=len, reverse=True))
    separator = (r"\b(?:but|while|whereas)\b|\band\b(?!\s+(?:" + categories + r")\b)"
                 r"|\bwith\b(?=\s*(?:" + names + r")\b)"
                 r"|,\s*with\s+(?:a|an)\s+|,(?=\s*(?:" + names + r"|highest|lowest|maximum|minimum|peak|trough)\b)")
    # A decimal point is part of a number, not a sentence boundary.
    sentences = re.split(r"(?<!\d)\.(?!\d)|(?<=\d)\.(?=\s|$)|[!?;\n]", text.lower())
    for sentence in sentences:
        previous = []
        pending = []
        for clause in re.split(separator, sentence):
            explicit = [n for n in series if re.search(word_pattern(n), clause)]
            # Preserve a shared subject in "sales and costs are lowest ...".
            if clause.strip() in series:
                pending.extend(n for n in explicit if n not in pending)
                previous = pending[:]
                continue
            subjects = explicit or previous
            if explicit and pending:
                subjects = list(dict.fromkeys(pending + explicit))
            pending = []
            if explicit:
                previous = subjects
            if subjects:
                yield clause.strip(), subjects


def is_negated(text):
    return bool(re.search(r"\b(?:not|never)\b|n['’]t\b", text))


def check_language(text, labels, series, f, verified, contradicted, unverifiable):
    for clause, subjects in claim_clauses(text, labels, series):
        if not clause:
            continue
        # Predictions and hypothetical claims cannot be checked as observations.
        if re.search(r"\b(?:will|would|could|might|if|expected|forecast\w*|predict\w*)\b", clause):
            if not find_cue(clause):
                unverifiable.append(f'The hypothetical claim "{clause}" cannot be confirmed from the data alone.')
            continue
        if re.search(r"\b(?:highest|lowest|largest|smallest|greatest|biggest|maximum|minimum)\s+(?:increase|decrease|rise|fall|growth|drop|change)\b|\b(?:increased|decreased|rose|fell|grew|dropped)\s+(?:the\s+)?(?:most|least)\b", clause):
            unverifiable.append(f'Change: comparing the size of changes in "{clause}" is not supported by this rule.')
            continue
        extrema = sorted([(m, 'max') for m in re.finditer(MAX_CUE, clause)] +
                         [(m, 'min') for m in re.finditer(MIN_CUE, clause)], key=lambda x: x[0].start())
        if len(subjects) > 1 and len(extrema) > 1:
            unverifiable.append(f'Extremum: cannot assign the claims in "{clause}" to individual series. '
                                'State each series claim separately.')
            continue
        for i, (cue, kind) in enumerate(extrema):
            # "Highest increase" describes a change, not the largest data value.
            tail = clause[cue.end():]
            if re.match(r"\s+(?:increase|decrease|rise|fall|growth|drop|change)\b", tail):
                continue
            end = extrema[i + 1][0].start() if i + 1 < len(extrema) else len(clause)
            context = clause[cue.end():end]
            mentions = label_mentions(context, labels)
            if not mentions and len(extrema) == 1:
                context = clause
                mentions = label_mentions(context, labels)
            indices = set(index for _, _, index in mentions)
            # Numbers inside category labels (e.g. Q1 or 2026) are not values.
            numbers = [to_number(m.group()) for m in re.finditer(NUMBER, context)
                       if not any(start <= m.start() < stop for start, stop, _ in mentions)]
            if (len(indices) > 1 and not re.search(r'\band\b', context)) or len(set(numbers)) > 1 or not (indices or numbers):
                unverifiable.append(f'Extremum: cannot identify a single category or value for "{clause}". '
                                    'State one maximum or minimum claim per clause.')
                continue
            for name in subjects:
                vals = series[name]
                extreme = f[name][kind][0]
                winners = [labels[j] for j, value in enumerate(vals) if value == extreme]
                matches = (not indices or all(vals[j] == extreme for j in indices)) and (
                    not numbers or abs(numbers[0] - extreme) <= 1e-9)
                if re.search(r"\b(?:only|sole|unique|uniquely)\b", clause) and len(winners) > 1:
                    matches = False
                negated = is_negated(clause[:cue.end()]) or bool(re.match(r"\s+(?:is |was )?not\b", tail))
                agrees = not matches if negated else matches
                heading, noun = ('Peak', 'maximum') if kind == 'max' else ('Minimum', 'minimum')
                statement = f'{heading}: the {noun} claim for {name}'
                if agrees:
                    verified.append(f'{statement} matches the data. The {noun} is {extreme:g} at {", ".join(winners)}.')
                else:
                    contradicted.append(f'{statement} conflicts with the data. The real {noun} is {extreme:g} at {", ".join(winners)}.')

        # An extremum sentence can include other verbs; avoid mistaking them for trends.
        if extrema:
            continue
        trends = [(direction, m) for direction, pattern in TREND_CUES.items()
                  for m in re.finditer(pattern, clause)]
        # "Steady increase" has direction as well as a continuity modifier.
        directional = [(d, m) for d, m in trends if d != 'flat']
        if directional:
            trends = directional
        if not trends:
            continue
        if len(set(d for d, _ in trends)) != 1:
            unverifiable.append(f'Trend: cannot isolate one trend claim in "{clause}".')
            continue
        claimed, cue = trends[0]
        for name in subjects:
            vals = series[name]
            category_indices = list(dict.fromkeys(j for _, _, j in label_mentions(clause, labels)))
            ranged = bool(re.search(r"\bfrom\b.*\bto\b|\bbetween\b.*\band\b", clause))
            start, end = 0, len(vals) - 1
            if ranged and len(category_indices) == 2:
                start, end = category_indices
            elif len(category_indices) == 1 and re.search(r'\b(?:in|at|during)\b', clause):
                end = category_indices[0]
                if end == 0:
                    unverifiable.append(f'Trend: no preceding category is available for {name} at {labels[end]}.')
                    continue
                start = end - 1
            elif category_indices:
                unverifiable.append(f'Trend: cannot resolve the range for {name} in "{clause}". '
                                    'Use "from <category> to <category>" for a local trend.')
                continue
            step = 1 if end >= start else -1
            points = list(range(start, end + step, step))
            selected = [vals[j] for j in points]
            real = 'rises' if selected[-1] > selected[0] else 'falls' if selected[-1] < selected[0] else 'flat'
            continuous = bool(re.search(r"\b(?:steadily|steady|continuously|consistently|monotonically|throughout)\b|\bevery\s+(?:month|quarter|year|interval)\b", clause))
            if claimed == 'flat' and not re.search(r"\boverall\b", clause):
                continuous = True
            agrees = real == claimed
            if continuous:
                differences = [b - a for a, b in zip(selected, selected[1:])]
                agrees = bool(differences) and all(delta > 0 if claimed == 'rises' else
                                                 delta < 0 if claimed == 'falls' else delta == 0
                                                 for delta in differences)
            # "Did not change" is itself a flat claim, not a negated flat claim.
            if is_negated(clause[:cue.end()]) and not re.fullmatch(r"(?:no change|(?:did|does|do) not change)", cue.group()):
                agrees = not agrees
            detail = (f'From {labels[start]} to {labels[end]}, the data go from {selected[0]:g} '
                      f'to {selected[-1]:g}.')
            if continuous:
                detail += ' Every adjacent pair was checked.'
            message = f'Trend: the claim for {name} ' + ('matches' if agrees else 'conflicts with') + f' the data. {detail}'
            (verified if agrees else contradicted).append(message)


def check(text, labels, series, f, unit):
    low = text.lower()
    verified, contradicted, unverifiable, missing, number_notes = [], [], [], [], []

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

    check_language(text, labels, series, f, verified, contradicted, unverifiable)

    # 1. Report number presence, but do not treat presence as claim verification.
    allvals = set().union(*[s["values"] for s in f.values()])
    seen = []
    for num in re.findall(NUMBER, text):
        if num in seen:
            continue
        seen.append(num)
        if to_number(num) in allvals:
            number_notes.append(
                f"The number {num} appears among the source values. This only records "
                "presence; it does not establish that the description uses it correctly."
            )
        else:
            number_notes.append(
                f"The number {num} was not found among the source values. Without matching "
                "it to a series, category, or transformation, this alone does not establish an error."
            )

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
        if not re.search(word_pattern(name), low):
            missing.append(f"The series {name} is in the data but is never mentioned.")

    return dict(verified=verified, contradicted=contradicted,
                unverifiable=unverifiable, missing=missing, number_notes=number_notes)


# ---------------------------------------------------------------------------
# 3. Report: plain sentences, summary first, so it reads well aloud
# ---------------------------------------------------------------------------

def plural(n, word, many=None):
    return f"{n} {word}" if n == 1 else f"{n} {many or word + 's'}"

def report(title, b):
    v, c, u, m = (len(b[k]) for k in ("verified", "contradicted", "unverifiable", "missing"))
    number_notes = b.get("number_notes", [])
    lines = [f"Report for {title}.",
             f"Summary: {plural(v + c + u, 'claim')} compared with the data. "
             f"Consistent details: {v}; conflicting details: {c}; "
             f"claims not assessable from these data: {u}; potentially missing items: {m}."]
    groups = [("verified", "Details consistent with the data"),
              ("contradicted", "Details that conflict with the data"),
              ("unverifiable", "Claims the data cannot assess"),
              ("missing", "Potentially missing items, present in the data but not the description")]
    for key, heading in groups:
        if b[key]:
            lines.append(f"{heading}: {len(b[key])}.")
            lines += b[key]
    if number_notes:
        lines.append(f"Number presence notes (not claim verification): {len(number_notes)}.")
        lines += number_notes
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
