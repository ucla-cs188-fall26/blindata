# Constraint checks

The checker compares supported English claims with the supplied chart data.
It returns verified, contradicted, unverifiable, and missing message buckets.
No LLM or API key is needed for these checks.

## Maximum and minimum claims

Recognized maximum expressions include `peak`, `peaks`, `peaked`, `peaking`,
`max`, `maximum`, `highest`, `largest`, `greatest`, `biggest`, `high point`,
`record high`, `all-time high`, `top value`, and `hit/reached a high`.

Minimum expressions include `min`, `minimum`, `lowest`, `smallest`, `fewest`,
`trough`, `bottomed out`, `low point`, `record low`, `all-time low`, and
`hit/reached a low`. Auxiliary words and tense variations are allowed:

- `Sales is the lowest in March.`
- `Sales reached its minimum in March.`
- `The highest sales occur in April.`
- `Sales peaked in April and are lowest in March.`
- `Sales is not lowest in January.`

The rule compares the claimed category and any stated extreme value with the
actual minimum or maximum. It accepts all tied extreme categories, not just
the first one. An `only`/`unique` extreme claim fails if the extreme is tied.
Full month names and abbreviations such as March/Mar and September/Sept/Sep
are equivalent; other category labels are matched literally, ignoring case.
Series names are matched as literal whole names.

Clauses separated by `and`, `but`, `while`, or `whereas` can refer to different
series. A subject can carry into the next clause of the same sentence. More
ambiguous statements are reported as unverifiable when the rule detects an
extreme claim but cannot resolve its category, value, or series attribution.
`Highest increase` is a claim about changes and is reported as unsupported;
it is not treated as the highest data value.

## Trend direction and continuity

Upward vocabulary includes rise/rose/rising, increase/increased/increasing,
grow/grew/growing, climb/climbed, go/went up, upward, and uptrend.
Downward vocabulary includes fall/fell/falling, decrease/decreased/decreasing,
decline/declined, drop/dropped, dip/dipped, shrink/shrank, go/went down,
downward, and downtrend.

Flat expressions include flat, stable, constant, unchanged, no change,
did not change, remained the same, and remained level.

- Overall rise/fall compares the first and last values.
- `Steadily`, `continuously`, `consistently`, `monotonically`, `throughout`,
  and `every month/quarter/year/interval` require every adjacent step to have
  the claimed direction. A flat step fails strict continuous increase/decrease.
- A flat/stable claim requires every adjacent value to be unchanged, unless
  `overall` explicitly limits it to the endpoints.
- `From February to March` or `between February and March` selects a range.
- A single category in a phrase such as `dipped in March` compares that
  category with the preceding data row. A first-row claim has no preceding
  evidence and is reported as unverifiable.
- Negation reverses the recognized predicate; for example, `did not increase
  continuously` is supported by a non-increasing interval.

Row order defines the sequence. The loader does not sort dates or infer missing
periods. "Steadily" currently checks direction, not equal rates of change.

## Other checks

- **Values:** distinct signed numbers, decimals, and comma-grouped values are
  checked for presence anywhere in the data. In a recognized extreme claim,
  the stated value must also match the actual extreme. General statements
  still do not fully bind a number to its claimed series/category.
- **Units:** recognized unit words are compared with available unit metadata
  or the `units` fallback. Arbitrary axis titles, ranges, scale factors, and
  currency conversions are not validated.
- **Completeness:** series names absent from the description are marked
  missing. Coverage of every unusual point is not implemented.
- **Unverifiable:** keyword cues identify causal, predictive, and judgmental
  statements. Future/hypothetical extrema and trends are not verified as
  observations of the supplied data.

## Limits

This is a deterministic language-rule prototype, not a general English parser.
Unknown synonyms or complex grammar can still be missed. Unsupported statements
are not all enumerated, so an empty error bucket does not prove the description
is correct. Comparisons between series, largest changes, pronoun resolution
across sentences, chart image extraction, and wording quality are outside the
current checks. Number presence is not proof of a correct numeric assertion.
