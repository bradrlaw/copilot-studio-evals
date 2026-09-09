# Conversation / User Troubleshooting Workbook

An operator-facing Azure Monitor Workbook for diagnosing a **single user** or a
**single conversation** across every Microsoft Copilot Studio agent that logs to
this Application Insights resource. It is deliberately separate from the
[GenAI Observability](observability-overview.md) workbook, which covers
agent/infrastructure-level trends (latency, tokens, cost, tool volume).

## What it answers

1. **How many sessions / conversations has a user had, across all agents?**
   (the *Users across all agents* grid)
2. **Find a conversation by user id / name _or_ conversation id.** (the
   *Conversations* finder — type either, or click a user)
3. **Show a conversation's messages.** (the *Conversation transcript* tile)
4. **Show a conversation's tool calls, inline with the messages** — a full flow
   of everything that happened. (the *Conversation flow* tile)

The *Conversations* finder also shows an **`approxToolCalls`** column — a
best-effort count of MCP tool calls per conversation (see
[the tool-call caveat](#the-tool-call-caveat-important)).

## Files

| Path | What |
| --- | --- |
| `../queries/conversation_troubleshooting_queries.kql` | Source-of-truth queries (Q0–Q4). |
| `../dashboards/build_troubleshooting_workbook.py` | Generates the workbook JSON from the `.kql`. |
| `../dashboards/conversation_troubleshooting_workbook.json` | The workbook — import into App Insights. |

## Deploy

Same flow as the observability workbook (see the
[deployment guide](deployment-guide.md) §Step 3):

1. (Only if you edited the `.kql`) regenerate:
   ```powershell
   python dashboards\build_troubleshooting_workbook.py
   ```
2. Azure portal → **Application Insights → Workbooks → New**, open the
   **Advanced Editor** (`</>`), clear the sample, paste the contents of
   `conversation_troubleshooting_workbook.json`, **Done Editing**, then **Save**
   scoped to this App Insights resource (e.g. name it *Conversation / User
   Troubleshooting*).

## How to use it

1. Set the **Time range** at the top (default 14 days). Optionally pick a single
   **Agent** (defaults to *— All agents —*).
2. **By user:** either type a **User id or name**, or click a row in *Users
   across all agents* — that pushes the user id into the filter and the
   *Conversations* grid lists their conversations. The field matches either a
   `fromId` (GUID / Teams MRI) or a **display name** (case-insensitive
   substring). Display names are only emitted on the **Teams (`msteams`)**
   channel; published-web (`pva-published-engine-direct`), `m365copilot` and
   `pva-studio` users are GUID-only, so name search won't find them.
3. **By conversation:** type a **Conversation id**, or click a row in
   *Conversations*. The **transcript** and **flow** tiles appear once a
   conversation id is set.
4. Read the **Conversation flow** tile for the full picture: user/agent messages
   interleaved with the MCP tool calls (with latency and outcome) that ran during
   the conversation.

## Identity model (how the telemetry maps)

Common Copilot Studio agent signals in App Insights:

| Concept | Where | Notes |
| --- | --- | --- |
| **Agent** | `customEvents.customDimensions.recipientName` on `BotMessageReceived` | On `BotMessageSend` this field can represent the *user*, so derive the agent only from received rows after confirming the local schema. |
| **User** | `customEvents.customDimensions.fromId` | Stable id per user. GUID on web/studio, a Teams MRI (`29:...`) on M365 Copilot. |
| **User display name** | `customEvents.customDimensions.recipientName` on `BotMessageSend` (keyed by `recipientId` == the user's `fromId`) | Only emitted on the **Teams (`msteams`)** channel; blank for published-web, m365copilot and studio. Used to let the *User id or name* filter match a name. |
| **Channel / surface** | prefix of the `user_Id` column | `pva-studio`, `pva-published-engine-direct`, `m365copilot`, `pva-maker-evaluation`. |
| **Conversation** | `customEvents.customDimensions.conversationId` | GUID *or* DirectLine `a:...` form. A single id can span **multiple sessions/days**. |
| **User message** | `BotMessageReceived` where `type == "message"` and `text != ""` | Excludes `conversationUpdate` / `installationUpdate` / `invoke` handshakes. |
| **Agent message** | `BotMessageSend` where `text != ""` | `type` is blank on send; filter on text. |
| **Tool call** | `dependencies` where `name == "mcp.tool"` | Tool name and outcome dimensions are provider-specific; `duration` and `success` use standard dependency columns. |

## The tool-call caveat (important)

`mcp.tool` rows carry **no `conversationId`, `user_Id`, or `session_Id`** — only
their own `operation_Id` (the MCP server’s own span). There is therefore **no id
to join a tool call to a conversation**. The *Conversation flow* tile overlays
tool calls onto the selected conversation by **timestamp window** (the
conversation’s first→last message time, ±30s). This is reliable when a user’s
conversations are spread out, but when **multiple conversations overlap in time**
a tool call in the window may belong to a different user. The messages themselves
are always exact (keyed on `conversationId`); only the tool overlay is
best-effort. The **`approxToolCalls`** column in the *Conversations* finder uses
the same timestamp-window correlation (per-conversation `dcount` of tool
`operation_Id`), so it is subject to the same overlap double-counting — treat it
as an at-a-glance indicator, not an exact total. Closing this gap would require
the platform to stamp a conversation/turn id onto the MCP tool telemetry (see
[gap analysis](app-insights-gap-analysis.md)).

## Regenerate / edit

The `.kql` is the single source of truth. Edit a query there, then re-run
`build_troubleshooting_workbook.py` to regenerate the workbook JSON and re-import
it. Queries reference the `{TimeRange}`, `{Agent}`, `{UserId}`, and
`{ConversationId}` parameters directly (no `ago()` rewrite), so they are embedded
verbatim.
