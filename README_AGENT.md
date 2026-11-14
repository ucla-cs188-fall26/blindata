# Blindata Interactive Evidence Agent — LLM Tool Calling Edition

This is a **drop-in add-on** for `ucla-cs188-fall26/blindata`. It does not overwrite the team's `checker.py`. It reuses `checker.load()`, `checker.facts()`, and `checker.check()` and provides grounded follow-up conversations with the OpenAI **Responses API function calling** workflow.

## Files

- `interactive_agent.py`: Existing `EvidenceAgent`, checker adapter, deterministic evidence methods, and the updated `ask()` entry point.
- `llm_agent.py`: LLM orchestration, strict read-only tool definitions, local tool dispatch, multi-turn history, evidence consolidation, guardrails, and the dependency-free API client.
- `agent_web.py`: Local HTTP server; no need to place an API key in the browser.
- `agent_ui.html` and `static/agent_ui.js`: Screen-reader-friendly evidence explorer UI.
- `test_interactive_agent.py`, `test_llm_agent.py`: Offline unit tests (no API calls).

## Installation

1. Clone or pull `https://github.com/ucla-cs188-fall26/blindata`.
2. The implementation files are already included in this repository; keep `static/` intact.
3. For LLM mode, set your API key **only in your terminal/server environment** (never in frontend JavaScript or Git):

   ```bash
   export OPENAI_API_KEY='your-api-key-here'
   export BLINDATA_AGENT_MODE=llm
   export BLINDATA_LLM_MODEL=gpt-6-luna
   python3 agent_web.py
   ```

   Open <http://127.0.0.1:8765>.

4. Or run directly in the terminal:

   ```bash
   python3 interactive_agent.py examples/chart1_data.csv examples/chart1_description_wrong.txt
   ```

   If your repository uses other example names, replace these sample paths with valid data and description paths.

5. Run both test suites:

   ```bash
   python3 -m unittest discover -v
   ```

**Modes:** `BLINDATA_AGENT_MODE=auto` (default) uses LLM when a key exists, otherwise old rule-based routing; `llm` requires a key; `rules` forces offline behavior. **Python standard library only**; no `pip install` is required.

Requires Python 3.9 or newer. The test suite also includes `test_agent_web.py`,
which starts a temporary local HTTP server and checks page delivery, every
example data format, follow-up evidence, and invalid requests without an API key.

## How the upgraded ask() works

```text
User asks a natural language question
    ↓
EvidenceAgent.ask() [auto / llm / rules]
    ↓ (llm)
LLM chooses strict read-only function calls
    ↓
Local dispatcher retrieves original dataset evidence
    ↓
Function results returned to LLM (Responses API)
    ↓
Model explains; numerical guard checks quantities against tool output
    ↓
Answer + original source rows shown in accessible HTML table
```

Tools include `list_findings`, `inspect_finding`, `get_source_rows`, `compare_points`, `get_extrema`, `get_trend`, `get_original_description`, and `get_suggested_description`.

The tool dispatcher validates label and series names against the reference dataset, computes trends from **all adjacent intervals**, pages source rows, and never lets the model run code or edit the checker results. Source data is represented as `row_index`, `label`, `series`, `value`; finding IDs remain local to the current report. The original checker returns message buckets, so this adapter cannot always pinpoint a precise claim's source row without a future structured checker-output change.

## Privacy, safety and limitations

### Troubleshooting HTTP 429

The client distinguishes known API error codes without displaying raw API error
messages or submitted chart content. `insufficient_quota` and
`credit_balance_exhausted` require checking credits and billing;
`project_spend_limit_exceeded`, `organization_spend_limit_exceeded`, and
`organization_usage_limit_exceeded` require reviewing the corresponding limits.
Repeated retries do not fix these account issues. `rate_limit_exceeded` and
`slow_down` indicate temporary rate limits: wait and reduce request frequency.
See the [official API error guide](https://developers.openai.com/api/docs/guides/error-codes).

### Data handling

- The initial checker runs locally. LLM mode sends **user questions and any chart information returned by requested tools** to the OpenAI API. Do not submit sensitive datasets without appropriate permission. Requests set `store=false` and do not persist API conversation state remotely through this client.
- The API key remains in the Python process environment, not browser scripts. For a public deployment, add authentication, CSRF protection, rate limiting, per-user sessions, and a production web server. This demo binds to `127.0.0.1` only.
- A bounded recent dialogue history is kept **in memory** per session and cleared when the local server stops.
- The model generates natural language and **can still make semantic mistakes**. The numerical guard is an extra check, not a guarantee. Always render the original evidence rows separately, and do not describe LLM narration as independently verified.
- If the LLM endpoint fails, the client reports an error instead of silently substituting a plausible explanation. Run `BLINDATA_AGENT_MODE=rules` to use explicit offline commands.
- The checker recognizes maximum/minimum synonyms and checks consecutive intervals for continuous/steady trends. Overall trends use endpoints; general label-to-number association and complex language remain limited. See `docs/constraints.md`. Tool-based `get_trend` does **not** silently rewrite the official checker verdict.
- API access and model permissions vary by account; default `gpt-6-luna` can be overridden with `BLINDATA_LLM_MODEL`.
- The test suite uses simulated Responses API outputs; it does not constitute a live API integration test or a VoiceOver/NVDA user study.
