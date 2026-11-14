# cs188-chart-checker

# CS 188 Core 3 prototype: chart description checker

Idea: a blind user gets a chart description (alt text / screen reader output) and
has no way to tell if it is right. This prototype checks a description against
the chart's actual data using a small set of constraints and reports, in plain
language: what matches, what conflicts, and what is missing.

## Core scenario

1. Input: a chart's data (CSV) + a text description of that chart.
2. Run the constraint checks (see `docs/constraints.md`).
3. Output: a short report a screen reader can read out:
   - matches: claims in the description that agree with the data
   - conflicts: claims that disagree with the data
   - missing: important things in the data the description never mentions

## Repo layout

- `docs/constraints.md` - the constraint list, what each check does
- `examples/` - test charts (data + description) with known right/wrong claims
- `checker.py` - first pass at running the checks on the examples

## Run the examples

```
python3 checker.py                              # built-in examples
python3 checker.py <data_file> <description_file>
```

## Interactive evidence explorer

Requires Python 3.9 or newer; uses only the Python standard library.
Start the local web interface from the repository directory:

```bash
BLINDATA_AGENT_MODE=rules python3 agent_web.py
```

Open http://127.0.0.1:8765, submit the sample data and description, then
inspect a finding or ask `compare sales February and March`.
Offline mode works without an API key.

For LLM follow-up questions, set `OPENAI_API_KEY` in the server environment
and run `BLINDATA_AGENT_MODE=llm python3 agent_web.py`.
See [README_AGENT.md](README_AGENT.md) for configuration, the terminal interface,
data handling, and limitations. Never put API keys in browser code or Git.

Run all offline tests, including the local HTTP integration tests:

```bash
python3 -m unittest discover -v
```

The LLM tests simulate API responses; a live LLM call requires an API key
and access to the configured model.

## Prototype status

Skeleton for Core Assignment 3 (first prototype). Demo: Nov 17.
