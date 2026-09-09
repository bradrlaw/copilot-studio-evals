# GenAI Observability (KQL + Dashboard)

Cost, token-usage, and tool-performance analytics for GenAI workloads whose
telemetry lands in **Application Insights**, spanning two platforms:

- **Azure AI Foundry** models & agents (OpenTelemetry GenAI semantic conventions)
- **Microsoft Copilot Studio** agents (environment-level OTel + legacy MCP path)

The tool-performance and model-usage signals land primarily in the App Insights
**`dependencies`** table, while classic Copilot Studio conversation messages use
**`customEvents`**. The queries normalize the relevant signals to a common shape. See
[`docs/app-insights-gap-analysis.md`](docs/app-insights-gap-analysis.md) for what
these signals **cannot** tell us (notably: Copilot Studio logs no tokens/cost).

## Contents

| Path | What |
| --- | --- |
| `queries/genai_observability_queries.kql` | The query set (Q0 discovery + Q1–Q5). Portal-runnable; `ago()`-based windows. |
| `dashboards/build_workbook.py` | Generates the Azure Monitor Workbook from the `.kql` (single source of truth). |
| `dashboards/genai_observability_workbook.json` | Generated workbook — import into App Insights. |
| `queries/conversation_troubleshooting_queries.kql` | Per-user / per-conversation troubleshooting query set (Q0–Q4). Workbook source of truth (parameterized). |
| `queries/conversation_troubleshooting_queries_standalone.kql` | Logs-pasteable twins of Q0–Q4 with editable `let` variables (`_start/_end/_agent/_userId/_convId`) instead of workbook params. |
| `dashboards/build_troubleshooting_workbook.py` | Generates the troubleshooting workbook from its `.kql`. |
| `dashboards/conversation_troubleshooting_workbook.json` | Generated troubleshooting workbook — import into App Insights. |
| `docs/conversation-troubleshooting.md` | What the troubleshooting workbook shows, identity model, and the tool-call caveat. |
| `docs/observability-overview.md` | What was built, how it works, data sources. |
| `docs/deployment-guide.md` | Manual deployment to an Azure environment (CI/CD later). |
| `docs/app-insights-gap-analysis.md` | What App Insights can/can't discern per platform; Dataverse gap-fill. |

## The queries

| # | Query | Works for |
| --- | --- | --- |
| 0 | Source discovery / telemetry inventory | both |
| 1 | Tool invocation frequency & error rate per tool | both |
| 2 | Token usage by model (daily; change bin to 7d for weekly) | AI Foundry only |
| 3 | Tool latency p50 / p95 / p99 per tool | both |
| 4 | Estimated cost per conversation (tokens × pricing) | AI Foundry only |
| 5 | Top-10 most expensive conversations | AI Foundry only |

> 💡 **Tip:** Run **Query 0 first** in any new environment to confirm which
> sources and `gen_ai.system` values are present before trusting Q1–Q5.

## Running the queries (portal)

Paste a query into **App Insights > Logs** and Run. Adjust the `ago(...)` window
as needed. Query 2 aggregates daily — change `bin(timestamp, 1d)` to
`bin(timestamp, 7d)` for weekly.

For shared use, save both query sets into an Azure Monitor query pack. Use the
`_standalone.kql` variants for raw Logs because that surface cannot resolve
workbook `{...}` parameters.

## Running from the command line

Reuse the repo's `../scripts/run_kql_query.py` (API-key or `az` mode). Behind an
SSL-inspecting proxy, set `REQUESTS_CA_BUNDLE` first.

```powershell
cd <REPOSITORY_ROOT>\telemetry
$env:REQUESTS_CA_BUNDLE = "$env:USERPROFILE\.azure\corp-ca-bundle.pem"
$py = "C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe"
& $py ..\scripts\run_kql_query.py --query 1 `
    --app-id <APP_ID> --api-key <KEY> `
    --kql-file queries\genai_observability_queries.kql --output q1.csv
```

## The dashboard (Azure Monitor Workbook)

1. Regenerate (only needed after editing the `.kql`):
   ```powershell
   python dashboards\build_workbook.py
   ```
2. In the Azure portal: **Application Insights > Workbooks > New**, open the
   **Advanced Editor** (`</>`), paste the contents of
   `dashboards/genai_observability_workbook.json`, click **Apply**, then **Save**.
3. Pick a **Time range** at the top; every tile is bound to it.

> 📝 **Note:** The workbook embeds copies of the queries with their `ago()` window
> swapped for the `{TimeRange}` parameter. `build_workbook.py` parses the `.kql`
> and performs that swap, so the `.kql` file stays the single source of truth —
> re-run it after any query change.

## Second workbook — Conversation / User troubleshooting

A separate, **operator-facing** workbook for drilling into a single user or
conversation (the observability workbook above is for agent/infra-level trends).
See [`docs/conversation-troubleshooting.md`](docs/conversation-troubleshooting.md).

It answers: how many sessions/conversations a user has had **across all agents**,
find a conversation by **user id or conversation id**, and show a conversation's
**messages with tool calls inline** (a full flow).

- Queries: `queries/conversation_troubleshooting_queries.kql` (Q0 agents, Q1
  users, Q2 conversation finder, Q3 transcript, Q4 flow).
- Generate: `python dashboards\build_troubleshooting_workbook.py`
- Import: same **Workbooks > New > Advanced Editor (`</>`)** paste-and-save flow,
  using `dashboards/conversation_troubleshooting_workbook.json`.

> ⚠️ **Warning:** MCP tool calls (`dependencies | name == "mcp.tool"`) carry **no
> conversation id / user id** — only their own `operation_Id`. The flow tile
> therefore overlays tool calls by **timestamp window**, which is best-effort
> when multiple conversations overlap in time. Messages themselves are exact
> (keyed on `customEvents.conversationId`).

## Before you trust cost numbers

> ⚠️ **Warning:** The pricing datatable in Queries 4 & 5 is a mid-2025 USD
> snapshot (Global/Standard). **Verify it against the live Azure OpenAI pricing
> page** before publishing figures; regional and PTU deployments differ. Models
> absent from the datatable are costed at 0 (visible via `pricedCalls < calls`).

## Conventions

- Vanilla, stdlib-only Python; no build step.
- KQL queries use the repo's `// QUERY <id>:` header convention (shared by
  `run_kql_query.py` and `build_workbook.py`).
- After changing a query, regenerate the workbook so it stays in sync.
