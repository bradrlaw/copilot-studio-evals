"""
Build the GenAI Observability Azure Monitor Workbook
====================================================
Parses ../queries/genai_observability_queries.kql (same `// QUERY <id>:` header
convention as the rest of the repo) and emits an Azure Monitor Workbook JSON
(gallery-template format) with one tile per query, wired to a shared TimeRange
parameter. Import the JSON via App Insights > Workbooks > New > Advanced Editor
(</> ) > paste > Apply.

stdlib only. Usage:
    python build_workbook.py            # writes genai_observability_workbook.json
    python build_workbook.py out.json
"""

import json
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
KQL_FILE = HERE.parent / "queries" / "genai_observability_queries.kql"
DEFAULT_OUT = HERE / "genai_observability_workbook.json"

QUERY_HEADER_RE = re.compile(r"^//\s*QUERY\s+([0-9A-Za-z]+)\s*:", re.IGNORECASE)
# Swap the ago()-based time filter for the workbook TimeRange parameter.
TIME_FILTER_RE = re.compile(r"where\s+timestamp\s*>\s*ago\([^)]*\)", re.IGNORECASE)
TIME_FILTER_SUB = "where timestamp between ({TimeRange:start} .. {TimeRange:end})"

# Per-query tile metadata: title, subtitle, and workbook visualization.
# visualization: "table" | "barchart" | "timechart" | "piechart"
TILES = {
    "0": ("Telemetry source inventory",
          "Which GenAI telemetry flavours are present (run to confirm your instance).",
          "table"),
    "1": ("Tool invocation frequency & error rate",
          "Per tool, across AI Foundry + Copilot Studio.",
          "barchart"),
    "2": ("Token usage by model (daily)",
          "AI Foundry only — Copilot Studio does not log tokens.",
          "timechart"),
    "3": ("Tool latency p50 / p95 / p99 (ms)",
          "Per tool; duration is milliseconds.",
          "table"),
    "4": ("Estimated cost per conversation (USD)",
          "AI Foundry only. Update the pricing datatable in the .kql.",
          "table"),
    "5": ("Top-10 most expensive conversations",
          "Highest token spend by conversation.",
          "table"),
}


def parse_queries(text: str) -> dict:
    """Return {query_id: kql_body} splitting on `// QUERY <id>:` headers and
    dropping comment-only lines (same behaviour as run_kql_query.py)."""
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
        if line.strip().startswith("//"):  # drop comment lines within the query
            continue
        queries[current].append(line)
    # Trim leading/trailing blank lines per query.
    out = {}
    for qid, lines in queries.items():
        body = "\n".join(lines).strip("\n")
        body = body.strip()
        if body:
            out[qid] = body
    return out


def to_workbook_query(body: str) -> str:
    return TIME_FILTER_RE.sub(TIME_FILTER_SUB, body)


def _id() -> str:
    return str(uuid.uuid4())


def text_item(markdown: str) -> dict:
    return {
        "type": 1,
        "content": {"json": markdown},
        "name": f"text - {_id()[:8]}",
    }


def query_item(title: str, subtitle: str, query: str, viz: str) -> dict:
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
        content["title"] = f"{title}"
        content["comment"] = subtitle
    return {
        "type": 3,
        "content": content,
        "name": f"query - {title[:20]}",
    }


def time_range_parameter() -> dict:
    durations = [5, 15, 30, 60, 4 * 60, 12 * 60, 24 * 60,
                 2 * 24 * 60, 7 * 24 * 60, 14 * 24 * 60, 30 * 24 * 60,
                 90 * 24 * 60]
    selectable = [{"durationMs": m * 60 * 1000} for m in durations]
    return {
        "type": 9,
        "content": {
            "version": "KqlParameterItem/1.0",
            "parameters": [
                {
                    "id": _id(),
                    "version": "KqlParameterItem/1.0",
                    "name": "TimeRange",
                    "label": "Time range",
                    "type": 4,
                    "isRequired": True,
                    "value": {"durationMs": 14 * 24 * 60 * 60 * 1000},
                    "typeSettings": {
                        "selectableValues": selectable,
                        "allowCustom": True,
                    },
                }
            ],
            "style": "pills",
            "queryType": 0,
            "resourceType": "microsoft.insights/components",
        },
        "name": "parameters - timerange",
    }


def build_workbook(queries: dict) -> dict:
    items = [
        text_item(
            "# GenAI Observability\n"
            "Cost, token usage, and tool performance across **Azure AI Foundry** "
            "and **Microsoft Copilot Studio** telemetry in this Application "
            "Insights resource. Token/cost tiles are populated for AI Foundry "
            "only — see the gap analysis in the repo. Pick a time range below."
        ),
        time_range_parameter(),
    ]
    for qid in ["0", "1", "2", "3", "4", "5"]:
        if qid not in queries or qid not in TILES:
            continue
        title, subtitle, viz = TILES[qid]
        items.append(text_item(f"## {title}\n{subtitle}"))
        items.append(query_item(title, subtitle,
                                 to_workbook_query(queries[qid]), viz))
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
