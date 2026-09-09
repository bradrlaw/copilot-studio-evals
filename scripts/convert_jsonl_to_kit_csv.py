"""
Eval JSONL -> Copilot Studio Kit (Agent Test) CSV Conversion Script
===================================================================
Converts the internal eval JSONL format into a CSV whose columns map to the
Power CAT Copilot Studio Kit "Agent Test" table, so rows can be pasted into the
Kit's "Export Agent Tests in Excel Online" sheet for bulk creation.

Usage:
    python convert_jsonl_to_kit_csv.py <input.jsonl> <output.csv> [options]

    # Examples
    python convert_jsonl_to_kit_csv.py eval.jsonl eval_kit.csv --test-set "Agent regression"

Mapping logic (one row per user turn):
    - Turn HAS expected_tool_calls  -> Test Type = "Plan Validation"
        Expected Tools  = comma-separated tool names (no spaces)
        Pass Threshold %= --pass-threshold (default 100)
    - Turn has a response pattern only -> Test Type = "Generative Answers"
        Expected Response = captured response pattern (used as validation hint)
        Expected Generative Answers Outcome = "Answered"
    - Otherwise -> Test Type = "Response Match" (Expected Response left blank)

Output columns (Kit Agent Test display names + two helper columns):
    Name, Agent Test Set, Test Type, Test Utterance, Expected Response,
    Expected Tools, Pass Threshold (%), Expected Generative Answers Outcome,
    Multiturn Conversation, Order

Notes:
    - "Multiturn Conversation" and "Order" are HELPER columns (not Kit fields).
      They let you assemble Kit multi-turn tests by grouping rows that share a
      conversation, in the given order. Remove them before pasting single-turn
      tests, or use them to build the parent multi-turn test + child tests.
    - Expected Tools uses the MCP tool names from telemetry (e.g.
      "record.search"). Adjust these to match the tool/plugin names as they
      appear in your agent's generative-orchestration plan if they differ.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

KIT_COLUMNS = [
    "Name",
    "Agent Test Set",
    "Test Type",
    "Test Utterance",
    "Expected Response",
    "Expected Tools",
    "Pass Threshold (%)",
    "Expected Generative Answers Outcome",
    "Multiturn Conversation",
    "Order",
]


def load_jsonl(path: Path) -> list:
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                lines.append(json.loads(raw))
    return lines


def group_by_conversation(lines: list) -> dict:
    conversations = {}
    for line in lines:
        cid = line.get("conversation_id", "")
        conversations.setdefault(cid, []).append(line)
    for cid in conversations:
        conversations[cid].sort(key=lambda t: t.get("turn_number", 0))
    return conversations


def tool_names(turn: dict) -> list:
    names = []
    for tc in turn.get("expected_tool_calls", []) or []:
        name = tc.get("tool", "").strip()
        if name and name not in names:
            names.append(name)
    return names


def short_conv_label(conversation_id: str, index: int) -> str:
    """Readable short label for grouping helper column."""
    return f"conv{index:03d}"


def convert(lines: list, test_set: str, pass_threshold: int, max_chars: int) -> list:
    conversations = group_by_conversation(lines)
    rows = []

    for conv_index, (_cid, turns) in enumerate(conversations.items(), start=1):
        conv_label = short_conv_label(_cid, conv_index)
        order = 0
        for turn in turns:
            utterance = (turn.get("user_message") or "").strip()
            if not utterance:
                continue
            order += 1
            utterance = utterance[:max_chars]

            tools = tool_names(turn)
            response_pattern = turn.get("expected_response_pattern") or ""

            if tools:
                test_type = "Plan Validation"
                expected_tools = ",".join(tools)
                expected_response = ""
                threshold = str(pass_threshold)
                gen_outcome = ""
            elif response_pattern:
                test_type = "Generative Answers"
                expected_tools = ""
                expected_response = response_pattern
                threshold = ""
                gen_outcome = "Answered"
            else:
                test_type = "Response Match"
                expected_tools = ""
                expected_response = ""
                threshold = ""
                gen_outcome = ""

            name = f"{conv_label}-t{order:02d}"
            rows.append({
                "Name": name,
                "Agent Test Set": test_set,
                "Test Type": test_type,
                "Test Utterance": utterance,
                "Expected Response": expected_response,
                "Expected Tools": expected_tools,
                "Pass Threshold (%)": threshold,
                "Expected Generative Answers Outcome": gen_outcome,
                "Multiturn Conversation": conv_label,
                "Order": order,
            })

    return rows


def write_csv(rows: list, path: Path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=KIT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="Convert eval JSONL to Copilot Studio Kit Agent Test CSV"
    )
    parser.add_argument("input", help="Input eval JSONL file")
    parser.add_argument("output", help="Output Kit Agent Test CSV file")
    parser.add_argument(
        "--test-set",
        default="Agent Evaluation Set",
        help="Value for the 'Agent Test Set' column (default: 'Agent Evaluation Set')",
    )
    parser.add_argument(
        "--pass-threshold",
        type=int,
        default=100,
        help="Plan Validation pass threshold percentage (default: 100)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=500,
        help="Max characters per test utterance (default: 500)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        sys.exit(1)

    lines = load_jsonl(input_path)
    rows = convert(lines, args.test_set, args.pass_threshold, args.max_chars)
    write_csv(rows, Path(args.output))

    # Summary
    from collections import Counter
    type_counts = Counter(r["Test Type"] for r in rows)
    conv_count = len({r["Multiturn Conversation"] for r in rows})
    print(f"Input:  {input_path}  ({len(lines)} turns)")
    print(f"Output: {args.output}  ({conv_count} conversations, {len(rows)} tests)")
    print("Test types:")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
