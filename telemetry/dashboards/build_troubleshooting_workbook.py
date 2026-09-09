"""
Build the Conversation / User Troubleshooting Azure Monitor Workbook
====================================================================
Parses ../queries/conversation_troubleshooting_queries.kql (same
`// QUERY <id>:` header convention as the rest of the repo) and emits an Azure
Monitor Workbook JSON (gallery-template format) for per-user / per-conversation
troubleshooting of Copilot Studio agents.

Unlike the observability workbook, these queries reference their parameters
({TimeRange}, {Agent}, {UserId}, {ConversationId}) directly, so no ago()->
TimeRange rewrite happens here — the query bodies are embedded verbatim.

Interactivity wired up here:
  - Agent picker (dropdown, "— All agents —" default) filters the user/finder grids.
  - Clicking a row in "Users" exports userId -> {UserId} (drives the finder).
  - Clicking a row in "Conversations" exports convId -> {ConversationId}
    (drives the transcript + flow tiles).
  - The transcript and flow tiles are hidden until a {ConversationId} is set
    (typed or clicked).

stdlib only. Usage:
    python build_troubleshooting_workbook.py            # -> conversation_troubleshooting_workbook.json
    python build_troubleshooting_workbook.py out.json
"""

import json
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
KQL_FILE = HERE.parent / "queries" / "conversation_troubleshooting_queries.kql"
DEFAULT_OUT = HERE / "conversation_troubleshooting_workbook.json"

QUERY_HEADER_RE = re.compile(r"^//\s*QUERY\s+([0-9A-Za-z]+)\s*:", re.IGNORECASE)

# Query id -> tile metadata.
#   title, subtitle, visualization,
#   export (field, param) to set on row click (or None),
#   requires_conversation (True -> tile hidden until {ConversationId} set)
TILES = {
    "0": ("Agents in this resource",
          "Every Copilot Studio agent (bot) that logs to this Application Insights resource.",
          "table", None, False),
    "1": ("Users across all agents",
          "Sessions & conversations per user (fromId + display name where available), across every agent. Type a user id or name in the filter, or click a row to load that user's conversations below.",
          "table", ("userId", "UserId"), False),
    "2": ("Conversations",
          "Find by user id and/or conversation id (or click a user above). approxToolCalls counts MCP tool calls by timestamp window (best-effort). Click a row to open the transcript & flow.",
          "table", ("convId", "ConversationId"), False),
    "3": ("Conversation transcript",
          "Ordered user/agent messages for the selected conversation.",
          "table", None, True),
    "4": ("Conversation flow (messages + tool calls)",
          "Messages interleaved with MCP tool calls. Tool calls are matched by TIMESTAMP WINDOW (they carry no conversation id) — treat as best-effort when conversations overlap in time.",
          "table", None, True),
}

# Parameter query for the Agent dropdown ("— All agents —" first, value == "").
AGENT_PARAM_QUERY = (
    "union\n"
    " (print value = \"\", label = \"\\u2014 All agents \\u2014\", ord = 0),\n"
    " (customEvents\n"
    "  | where timestamp between ({TimeRange:start} .. {TimeRange:end})\n"
    "  | where name == \"BotMessageReceived\"\n"
    "  | extend agent = tostring(customDimensions.recipientName)\n"
    "  | where isnotempty(agent)\n"
    "  | distinct agent\n"
    "  | project value = agent, label = agent, ord = 1)\n"
    "| order by ord asc, label asc\n"
    "| project value, label"
)


def parse_queries(text: str) -> dict:
    """Return {query_id: kql_body}; drop comment-only and blank lines, matching
    run_kql_query.py / build_workbook.py behaviour."""
    queries: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = QUERY_HEADER_RE.match(line.strip())
        if m:
            current = m.group(1)
            queries[current] = []
            continue
        if current is None:
            continue
        if line.strip().startswith("//"):
            continue
        queries[current].append(line)
    out = {}
    for qid, lines in queries.items():
        body = "\n".join(lines).strip()
        if body:
            out[qid] = body
    return out


def _id() -> str:
    return str(uuid.uuid4())


def text_item(markdown: str) -> dict:
    return {"type": 1, "content": {"json": markdown}, "name": f"text - {_id()[:8]}"}


def query_item(qid, title, subtitle, query, viz, export, requires_conversation) -> dict:
    content = {
        "version": "KqlItem/1.0",
        "query": query,
        "size": 0,
        "title": title,
        "queryType": 0,
        "resourceType": "microsoft.insights/components",
        "visualization": viz,
    }
    if subtitle:
        content["comment"] = subtitle
    if export:
        field, param = export
        # Row-click -> set a text parameter (parameterType 1).
        content["exportedParameters"] = [
            {"fieldName": field, "parameterName": param, "parameterType": 1}
        ]
    item = {"type": 3, "content": content, "name": f"query - {qid} {title[:18]}"}
    if requires_conversation:
        item["conditionalVisibility"] = {
            "parameterName": "ConversationId",
            "comparison": "isNotEqualTo",
            "value": "",
        }
    return item


def parameters_item() -> dict:
    durations = [15, 30, 60, 4 * 60, 12 * 60, 24 * 60,
                 2 * 24 * 60, 7 * 24 * 60, 14 * 24 * 60, 30 * 24 * 60, 90 * 24 * 60]
    time_range = {
        "id": _id(),
        "version": "KqlParameterItem/1.0",
        "name": "TimeRange",
        "label": "Time range",
        "type": 4,
        "isRequired": True,
        "value": {"durationMs": 14 * 24 * 60 * 60 * 1000},
        "typeSettings": {
            "selectableValues": [{"durationMs": m * 60 * 1000} for m in durations],
            "allowCustom": True,
        },
    }
    agent = {
        "id": _id(),
        "version": "KqlParameterItem/1.0",
        "name": "Agent",
        "label": "Agent",
        "type": 2,
        "isRequired": False,
        "value": "",
        "query": AGENT_PARAM_QUERY,
        "queryType": 0,
        "resourceType": "microsoft.insights/components",
        "typeSettings": {"additionalResourceOptions": []},
    }
    user_id = {
        "id": _id(),
        "version": "KqlParameterItem/1.0",
        "name": "UserId",
        "label": "User id or name",
        "type": 1,
        "isRequired": False,
        "value": "",
    }
    conversation_id = {
        "id": _id(),
        "version": "KqlParameterItem/1.0",
        "name": "ConversationId",
        "label": "Conversation id",
        "type": 1,
        "isRequired": False,
        "value": "",
    }
    return {
        "type": 9,
        "content": {
            "version": "KqlParameterItem/1.0",
            "parameters": [time_range, agent, user_id, conversation_id],
            "style": "pills",
            "queryType": 0,
            "resourceType": "microsoft.insights/components",
        },
        "name": "parameters - filters",
    }


def build_workbook(queries: dict) -> dict:
    items = [
        text_item(
            "# Conversation / User Troubleshooting\n"
            "Diagnose a specific **user** or **conversation** for any Copilot "
            "Studio agent in this Application Insights resource. Pick a time "
            "range, then either type a **user id** / **conversation id** or "
            "click through the grids below (user \u2192 conversations \u2192 "
            "transcript & flow).\n\n"
            "> \u26a0\ufe0f **Tool-call caveat:** MCP tool calls (`mcp.tool`) carry no "
            "conversation id, so the flow tile overlays them by **timestamp "
            "window** \u2014 best-effort when conversations overlap in time."
        ),
        parameters_item(),
    ]
    for qid in ["0", "1", "2", "3", "4"]:
        if qid not in queries or qid not in TILES:
            continue
        title, subtitle, viz, export, requires_conversation = TILES[qid]
        items.append(text_item(f"## {title}\n{subtitle}"))
        items.append(query_item(qid, title, subtitle, queries[qid], viz,
                                 export, requires_conversation))
    return {
        "version": "Notebook/1.0",
        "items": items,
        "isLocked": False,
        "fallbackResourceIds": [],
        "$schema": "https://github.com/Microsoft/Application-Insights-Workbooks/blob/master/schema/workbook.json",
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    queries = parse_queries(KQL_FILE.read_text(encoding="utf-8"))
    missing = [q for q in TILES if q not in queries]
    if missing:
        print(f"Warning: queries not found in {KQL_FILE.name}: {missing}")
    wb = build_workbook(queries)
    out.write_text(json.dumps(wb, indent=2), encoding="utf-8")
    print(f"Wrote workbook with {sum(1 for i in wb['items'] if i['type'] == 3)} "
          f"query tiles -> {out}")


if __name__ == "__main__":
    main()
