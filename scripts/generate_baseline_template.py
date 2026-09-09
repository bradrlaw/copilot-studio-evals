#!/usr/bin/env python3
"""Generate a baseline results-recording template (CSV) from an eval JSONL file.

The template has one row per evaluation turn, pre-filled with the expected behavior
(utterance, expected tools, response pattern, pass criteria, category) and blank
columns for the tester to record the baseline run outcome (Result, Actual Response,
Actual Tools, Notes, Run Date, Run Target).

This is agent-agnostic: it works with any JSONL that follows the eval schema. The grouping
column defaults to `category`; use `--group-by` for another traceability field.

Usage:
    python generate_baseline_template.py eval_scenarios.jsonl baseline_results_template.csv
    python generate_baseline_template.py eval_scenarios.jsonl out.csv --skip-agent-turns
    python generate_baseline_template.py eval.jsonl out.csv --group-by category
"""
import argparse
import csv
import json


def summarize_tool_calls(calls):
    """Render expected_tool_calls as a compact, human-readable string."""
    parts = []
    for tc in calls or []:
        tool = tc.get("tool", "")
        params = tc.get("params") or {}
        entity = params.get("entity")
        via = tc.get("via_agent")
        piece = tool
        if entity:
            piece += f"({entity})"
        if via:
            piece += f" via {via}"
        parts.append(piece)
    return "; ".join(parts)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# Columns the tester fills in during/after the baseline run.
RESULT_COLUMNS = [
    "Run Date",
    "Run Target",       # "Copilot Studio" | "Kit"
    "Result",           # PASS | FAIL | BLOCKED
    "Actual Tools",
    "Actual Response",
    "Notes",
]

EXPECTED_COLUMNS = [
    "conversation_id",
    "turn_number",
    "{group}",          # placeholder — replaced with the --group-by column name
    "pass_criteria",
    "user_message",
    "expected_tool_calls",
    "must_not_call",
    "expected_response_pattern",
    "response_must_not_match",
]


def main():
    ap = argparse.ArgumentParser(description="Generate a baseline results template from eval JSONL")
    ap.add_argument("input", help="Input eval JSONL file")
    ap.add_argument("output", help="Output baseline results CSV template")
    ap.add_argument("--skip-agent-turns", action="store_true",
                    help="Skip turns with no user_message (agent-only response turns)")
    ap.add_argument("--group-by", default="category",
                    help="JSONL field to carry through as the grouping column "
                         "(default: category)")
    args = ap.parse_args()

    group = args.group_by
    rows = load_jsonl(args.input)
    out_rows = []
    for r in rows:
        if args.skip_agent_turns and not r.get("user_message"):
            continue
        out_rows.append({
            "conversation_id": r.get("conversation_id", ""),
            "turn_number": r.get("turn_number", ""),
            group: r.get(group, ""),
            "pass_criteria": r.get("pass_criteria", ""),
            "user_message": r.get("user_message") or "",
            "expected_tool_calls": summarize_tool_calls(r.get("expected_tool_calls")),
            "must_not_call": ", ".join(r.get("must_not_call") or []),
            "expected_response_pattern": r.get("expected_response_pattern") or "",
            "response_must_not_match": r.get("response_must_not_match") or "",
            # blank result columns
            "Run Date": "",
            "Run Target": "",
            "Result": "",
            "Actual Tools": "",
            "Actual Response": "",
            "Notes": "",
        })

    columns = [group if c == "{group}" else c for c in EXPECTED_COLUMNS] + RESULT_COLUMNS
    # UTF-8 BOM so Excel opens it cleanly.
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(out_rows)

    convs = len({r["conversation_id"] for r in out_rows})
    print(f"Input:  {args.input}  ({len(rows)} turns)")
    print(f"Output: {args.output}  ({len(out_rows)} rows, {convs} conversations)")
    print(f"Grouping column: {group}")
    print(f"Fill in these columns during the run: {', '.join(RESULT_COLUMNS)}")


if __name__ == "__main__":
    main()
