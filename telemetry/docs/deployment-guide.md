# GenAI Observability — Deployment Guide (Manual)

How to deploy the observability package to an Azure environment **manually**.
CI/CD automation is planned separately; every step here is portal/CLI-driven and
idempotent.

> 📝 **Note:** "Deploy" here means: (1) make sure both platforms export telemetry
> to an Application Insights resource, (2) publish the KQL queries, and (3) import
> the Workbook dashboard scoped to that resource. The queries and workbook are
> content on top of App Insights — there is no service to host.

---

## 1. Prerequisites

| Requirement | Notes |
| --- | --- |
| An **Application Insights** resource | The single sink both platforms export to. Log Analytics (workspace-based) recommended. |
| **Reader** (min) on that App Insights resource | To run Logs queries and view the workbook. **Contributor** to save a shared workbook. |
| Azure portal access | For Logs, Workbooks, and enabling exports. |
| **Python 3.9+** | Only to regenerate the workbook (`build_workbook.py`). stdlib only — no `pip install`. |
| (Optional) corporate proxy CA | If running queries via CLI behind SSL inspection, set `REQUESTS_CA_BUNDLE` (see §6). |

> ⚠️ **Warning:** Point all sources at **one** App Insights resource if you want a
> single dashboard. Cross-resource queries are possible but complicate the
> workbook scope; start with one resource per environment (dev / uat / prod).

---

## 2. Step 1 — Ensure telemetry is flowing to App Insights

### 2a. Azure AI Foundry (models & agents)
1. In the **Azure AI Foundry** portal, open your **project → Tracing** (or
   **Monitoring**) and **connect** the Application Insights resource from §1.
2. In the application code, enable OpenTelemetry GenAI tracing and export to that
   App Insights connection string, e.g. with `azure-monitor-opentelemetry`
   (`configure_azure_monitor(...)`) and the Azure AI tracing enabled.
3. To capture token usage you only need spans (tokens are span attributes). To
   also capture prompt/response **content**, set the content-recording opt-in
   (`AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED=true`) — optional and has
   privacy implications.

> 💡 **Tip:** Confirm arrival: **App Insights → Logs →**
> `dependencies | where timestamp > ago(1h) | where customDimensions has "gen_ai" | take 10`.

### 2b. Copilot Studio — environment-level telemetry (preview, OTel)
1. In the **Power Platform Admin Center → Environments →** *your environment* **→
   Settings**, find the **Application Insights / telemetry export** option and set
   the destination to the App Insights resource from §1.
2. This produces `dependencies` rows (`type == "GenAI"`, `name` =
   `InvokeAgent` / `ExecuteTool` / `OutputMessages`) with `gen_ai.*` dimensions.

### 2c. Copilot Studio — agent-level telemetry (classic, optional)
1. In **Copilot Studio → your agent → Settings → Advanced / Metadata**, connect
   the App Insights resource (instrumentation key / connection string).
2. Enable **Log conversation details** if you want message text (privacy
   implications). This produces `customEvents` (`BotMessageReceived` /
   `BotMessageSend`). Some legacy MCP integrations also emit
   `dependencies | name == "mcp.tool"`; confirm this with a discovery query.

> 📝 **Note:** Exact menu labels shift between portal releases — verify in your
> tenant. Env-level export is the modern, OTel-aligned path and is preferred.

> ⚠️ **Warning:** Copilot Studio will **not** emit token counts on any of these
> paths. Do not expect Queries 2/4/5 to populate for Copilot Studio traffic.

---

## 3. Step 2 — Publish the KQL queries

The queries need no deployment to *run* (paste into **App Insights → Logs**), but
publish them so the team shares one copy. There are **two** query files:

| File | Category | Notes |
| --- | --- | --- |
| `queries/genai_observability_queries.kql` | *GenAI Observability* | Q0–Q5. Use `ago()` windows — paste-and-run as-is. |
| `queries/conversation_troubleshooting_queries_standalone.kql` | *Conversation Troubleshooting* | Q0–Q4. Logs-pasteable twins of the workbook queries; edit the `let _start/_end/_agent/_userId/_convId` variables at the top before running. |

**Option A — Query pack / shared "Saved queries" (recommended):**
1. **App Insights → Logs**, paste a query from either `.kql` file above.
2. **Save → Save as query**, scope it to the App Insights resource, save it into
   the **`GenAI Observability`** query pack with the **Category** from the table
   above. Repeat per query. These land in a **query pack** shared with anyone who
   has access to the resource.

**Option B — Just keep them in the repo** and paste ad-hoc. Fine for one-off use.

> 💡 **Tip:** Run **Query 0** first in each new environment to confirm which
> sources and `gen_ai.system` values are present. For the troubleshooting
> queries, set `_convId` before running Q3/Q4.

---

## 4. Step 3 — Deploy the Workbook dashboard

1. **(Only if you edited the `.kql`)** regenerate the JSON:
   ```powershell
   python dashboards\build_workbook.py
   ```
2. Azure portal → **Application Insights →** *your resource* **→ Workbooks →
   New**.
3. Open the **Advanced Editor** (the `</>` icon), select **Gallery Template**,
   delete the sample JSON, and **paste** the entire contents of
   `dashboards/genai_observability_workbook.json`. Click **Apply**.
4. Confirm the tiles render, then **Save** (💾): give it a name (e.g.
   *GenAI Observability*), pick a **resource group / subscription**, and set the
   **workbook resource** scope to this App Insights resource.
5. (Optional) **Pin to a dashboard** or share the workbook link.

> 📝 **Note:** The workbook's queries reference a **`{TimeRange}`** parameter
> instead of `ago()`. Pick a time range at the top of the workbook; all tiles
> update together. Default is 14 days.

> ⚠️ **Warning:** If tiles show *"resource not set"* or empty, re-check that the
> workbook was **saved scoped to the App Insights resource** (step 4), not a bare
> subscription.

---

## 5. Step 4 — Set the model pricing

Queries 4 & 5 cost using an in-query `pricing` datatable (USD per 1,000,000
tokens, mid-2025 Global/Standard snapshot).

1. Open `queries/genai_observability_queries.kql`, find the `let pricing =
   datatable(...)` block (present in Q4 **and** Q5 — keep them identical).
2. Update rows against the live
   [Azure OpenAI pricing page](https://azure.microsoft.com/en-us/pricing/details/azure-openai/),
   adding any models you deploy.
3. Re-run `build_workbook.py` so the dashboard picks up the new pricing.

> ⚠️ **Warning:** Models missing from the datatable are costed at **0** (visible
> via `pricedCalls < calls` in Query 4). Treat all cost output as an estimate.

---

## 6. Step 5 — Validate the deployment

Run these in **App Insights → Logs** (or via CLI, §7):

1. **Q0** — expect ≥1 `source` row for each platform you enabled.
2. **Q1 / Q3** — expect tool rows once the agent has taken tool-using turns.
3. **Q2 / Q4 / Q5** — expect rows **only** if AI Foundry (token-bearing) traffic
   exists; empty is correct for Copilot-only environments.

> 💡 **Tip:** Telemetry can lag a few minutes. If Q0 is empty, widen the window
> (`ago(1d)`) and re-check the source enablement in Step 1.

---

## 7. (Optional) Run queries from the command line

The repo's `../scripts/run_kql_query.py` can execute any query in the `.kql` file
headlessly (API-key or `az` auth). Behind an SSL-inspecting proxy, export the CA
bundle first:

```powershell
cd <REPOSITORY_ROOT>\telemetry
$env:REQUESTS_CA_BUNDLE = "$env:USERPROFILE\.azure\corp-ca-bundle.pem"
$py = "C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe"
& $py ..\scripts\run_kql_query.py --query 1 `
    --app-id <APP_INSIGHTS_APP_ID> --api-key <KEY> `
    --kql-file queries\genai_observability_queries.kql --output q1.csv
```

Get the **Application ID** + an **API key** from **App Insights → Configure → API
Access**.

---

## 8. Per-environment rollout & teardown

- **Rollout:** repeat Steps 1–4 for each environment (dev / uat / prod), each with
  its own App Insights resource and its own saved workbook.
- **Teardown:** delete the saved workbook; remove saved queries; disable the
  telemetry exports in Step 1. No other footprint.

> 📝 **Note (CI/CD, future):** the workbook JSON can be deployed as an ARM
> resource (`microsoft.insights/workbooks`) and the saved queries as
> `microsoft.insights/querypacks` — wire these into a pipeline later. For now,
> manual import is the supported path.
