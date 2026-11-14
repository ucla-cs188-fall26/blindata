# Blindata: chart description checker and evidence explorer

Blindata helps a blind or low-vision reader compare a chart's text description
with its underlying data, then investigate the results through an interactive
agent. The existing checker runs first; the agent explains findings and retrieves
original data evidence. You can use the entire workflow offline, or enable an
OpenAI model for natural-language follow-up questions.

## 1. Install the prerequisites

You need:

- **Python 3.9 or newer.** Install from [python.org](https://www.python.org/downloads/).
- **Git.** Install from [git-scm.com](https://git-scm.com/downloads).
- A web browser for the web interface.
- Optional: an OpenAI API key with available quota and access to the configured
  model, if you want LLM follow-up questions.

Check your installation in a terminal:

```bash
git --version
python3 --version
```

On Windows, use `python` instead of `python3` in every command below. If neither
command is available, finish installing Python and reopen your terminal.

The project uses only the Python standard library. **No pip packages, Node.js,
frontend build, or separate agent installation are required.**

## 2. Download the entire project

```bash
git clone https://github.com/ucla-cs188-fall26/blindata.git
cd blindata
```

If you already cloned it, open a terminal in that folder and update it:

```bash
git pull --ff-only
```

Run all remaining commands from this repository directory. Keep `static/`,
`agent_ui.html`, and the Python files together.

## 3. Start the web app offline

Start here to confirm the complete local workflow works without an API key.

On macOS or Linux:

```bash
export BLINDATA_AGENT_MODE=rules
python3 agent_web.py
```

On Windows PowerShell:

```powershell
$env:BLINDATA_AGENT_MODE = 'rules'
python agent_web.py
```

Leave the terminal running and open [http://127.0.0.1:8765](http://127.0.0.1:8765).
Open this address through the Python server; opening `agent_ui.html` directly
will not start the backend. Press **Ctrl+C** in the terminal to stop the server.

## 4. Complete an end-to-end example

1. In the web page, select **CSV** as the data format.
2. Paste the following into **Reference chart data** (the page also includes
   this sample by default):

   ```csv
   Month,Sales
   Jan,100
   Feb,120
   Mar,90
   Apr,150
   ```

3. Paste this into **Accessible description**:

   ```text
   Sales peak in March. Sales rise overall.
   ```

4. Click **Run verification**. The backend loads the data, computes facts, and
   calls the existing checker's rules. Expect one contradicted peak claim
   (the actual peak is 150 in April) and one verified overall trend claim
   (100 in January to 150 in April).
5. Click a finding button to explore its explanation and evidence. The most
   recently activated button keeps a gold border.
6. Enter `compare sales February and March` in **Your question**, then click
   **Ask**. Expect values of 120 and 90, a change of -30, and a percentage
   change of -25.0%. The source evidence table shows the original data points.
7. Try **Show summary**, **Show evidence**, and **Suggested description**.
   Suggested text is labeled separately from your original description.
8. Replace the sample with your own data and description, then click
   **Run verification** again to create a new report and conversation.

In offline mode, use supported commands such as `summary`, `why 1`,
`show original values for sales`, `compare sales February and March`,
`maximum sales`, and `corrected description`.

The data must come from the chart's underlying table or supported specification;
this prototype does not extract values from a chart screenshot or image.

## 5. Enable LLM follow-up questions (optional)

Create a key in [OpenAI Platform API Keys](https://platform.openai.com/api-keys).
Set it in the **same terminal that starts the server**. The client reads
`OPENAI_API_KEY` from the process environment; it does not automatically load a
`.env` file. See the [official OpenAI quickstart](https://developers.openai.com/api/docs/quickstart).

Stop any running server with **Ctrl+C**, then run the following.

On macOS or Linux:

```bash
export OPENAI_API_KEY='replace-with-your-api-key'
export BLINDATA_AGENT_MODE=llm
export BLINDATA_LLM_MODEL=gpt-4.1-mini
python3 agent_web.py
```

On Windows PowerShell:

```powershell
$env:OPENAI_API_KEY = 'replace-with-your-api-key'
$env:BLINDATA_AGENT_MODE = 'llm'
$env:BLINDATA_LLM_MODEL = 'gpt-4.1-mini'
python agent_web.py
```

These settings apply to the current terminal session. Refresh the page, click
**Run verification** again, and ask, for example:

- `Why is the peak claim wrong?`
- `Did sales increase continuously? Show the evidence.`
- `Compare sales February and March.`

The initial checker still runs locally. For follow-up questions, the model
chooses read-only tools; the server retrieves or computes evidence from the
same dataset, then returns an explanation and original evidence rows. The
agent does not change the original checker verdicts.

Never commit your key or put it in browser JavaScript. In LLM mode, questions
and chart information returned by tools are sent to OpenAI. Use data you are
permitted to send. If the model is unavailable, the app reports the failure.

| Environment variable | Behavior |
| --- | --- |
| `BLINDATA_AGENT_MODE=rules` | Offline commands; no API calls, even if a key is set. |
| `BLINDATA_AGENT_MODE=llm` | Requires a key for follow-up answers. |
| `BLINDATA_AGENT_MODE=auto` | Default: uses LLM if a key exists, otherwise offline commands. |
| `OPENAI_API_KEY` | API key used by the Python backend. |
| `BLINDATA_LLM_MODEL` | Model name; defaults to `gpt-4.1-mini`. Must be accessible to your API project. |

## 6. Use the checker and agent in the terminal

Run the original checker on both built-in descriptions:

```bash
python3 checker.py
```

Or check a specific data/description pair:

```bash
python3 checker.py examples/chart1_data.csv examples/chart1_description_wrong.txt
```

Start an interactive conversation about the same report:

```bash
python3 interactive_agent.py examples/chart1_data.csv examples/chart1_description_wrong.txt
```

This prints the checker findings, then accepts questions at the `You:` prompt.
Use `help` for offline commands and `quit` to exit. It uses the same environment
variables as the web app, so set `BLINDATA_AGENT_MODE=rules` for offline use or
configure LLM mode as above. The terminal interface does not require the web server.

## 7. Prepare your own input files

Supported formats are CSV, TSV, tab-separated or whitespace-aligned pasted text,
JSON label/series objects, JSON row objects, and supported Vega-Lite specs with
inline `data.values`. In the web interface, choose **JSON** for a Vega-Lite spec.
See [examples/README.md](examples/README.md) for sample files in every format.

For CSV or TSV, include a header, put category labels in the first column, and
use numeric values in the remaining series columns. Include at least one data
row and one series, with a value for every category in every series. Store
file-based descriptions as UTF-8 text.

Reports group findings into verified, contradicted, unverifiable, and missing
items. These are rule-based checks, not a guarantee that every statement is
correct. For example, the core trend check uses endpoints, while the agent's
LLM trend tool can inspect adjacent intervals. The core numeric check does not
fully associate each number with its claimed category. Model explanations can
also be wrong; inspect the original source evidence.

## 8. Run the tests

```bash
python3 -m unittest discover -v
```

The suite covers the checker adapter, evidence operations, simulated LLM tool
calls, API error handling, and local HTTP integration across all seven example
formats. It requires no API key and makes no external API calls. The HTTP tests
start a temporary server on an available local port. Live model access and
screen-reader usability studies are separate from these automated tests.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Browser cannot connect | Keep `python3 agent_web.py` running and open `http://127.0.0.1:8765`. Check the terminal for startup errors. |
| `Address already in use` | Stop the previous server with Ctrl+C in its terminal, then start one instance. |
| Page still shows old buttons or wording | Refresh the page (hard refresh if necessary), then click **Run verification** again. Restart the server after Python changes. |
| `LLM mode requires OPENAI_API_KEY` | Set the key in the terminal used to launch Python, then restart the server. |
| HTTP 401 | Check that the API key is correct, active, and permitted to access the endpoint. |
| HTTP 429 with `insufficient_quota` or `credit_balance_exhausted` | Check [API billing](https://platform.openai.com/settings/organization/billing/overview) and credits before retrying. |
| HTTP 429 with a spend or usage limit code | Review the relevant project or organization [limits](https://platform.openai.com/settings/organization/limits). |
| HTTP 429 with `rate_limit_exceeded` or `slow_down` | Wait before retrying and reduce request frequency. |
| Model or permission error | Check that the API project can access the model named by `BLINDATA_LLM_MODEL`. |
| `Session expired` | Click **Run verification** again. Sessions are in memory and disappear on restart or eviction. |
| Invalid input or request too large | Check the selected format, table headers, and numeric values. The web API accepts request bodies up to 1 MB. |

For API failures, see the [official error guide](https://developers.openai.com/api/docs/guides/error-codes).
To continue offline, stop the server and repeat step 3.

The web server is a local prototype bound to `127.0.0.1`; it is not configured
for public hosting. See [README_AGENT.md](README_AGENT.md) for agent architecture,
data handling, and further limitations.

## Repository layout

| Path | Purpose |
| --- | --- |
| `checker.py` | Original data loading, facts, constraint checks, and report CLI. |
| `interactive_agent.py` | Checker adapter, local evidence operations, and interactive CLI. |
| `llm_agent.py` | Responses API client and read-only tool orchestration. |
| `agent_web.py` | Local HTTP server connecting the checker and agent to the UI. |
| `agent_ui.html`, `static/agent_ui.js` | Accessible web interface and interactions. |
| `examples/` | Equivalent data formats and descriptions with known findings. |
| `docs/constraints.md` | Constraints and checker behavior. |
| `test_*.py` | Offline unit and HTTP integration tests. |
| `README_AGENT.md` | Detailed agent documentation. |
