#!/usr/bin/env python3
"""Validate canonical evaluation JSONL files using the framework contract."""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


REQUIRED_FIELDS = {
    "conversation_id",
    "turn_number",
    "user_message",
    "expected_tool_calls",
    "expected_response_pattern",
    "pass_criteria",
    "category",
}
PASS_CRITERIA = {"tool_called_correctly", "response_matches", "both"}


def validate_file(path):
    errors = []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append("{}:{} invalid JSON: {}".format(path, line_number, exc.msg))
                continue
            rows.append((line_number, row))

    turns = defaultdict(list)
    seen_keys = set()
    for line_number, row in rows:
        prefix = "{}:{}".format(path, line_number)
        if not isinstance(row, dict):
            errors.append("{} must contain a JSON object".format(prefix))
            continue
        missing = REQUIRED_FIELDS - set(row)
        if missing:
            errors.append("{} missing fields: {}".format(prefix, ", ".join(sorted(missing))))
            continue

        conversation_id = row["conversation_id"]
        turn_number = row["turn_number"]
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            errors.append("{} conversation_id must be a non-empty string".format(prefix))
        if not isinstance(turn_number, int) or isinstance(turn_number, bool) or turn_number < 1:
            errors.append("{} turn_number must be a positive integer".format(prefix))
        elif isinstance(conversation_id, str):
            key = (conversation_id, turn_number)
            if key in seen_keys:
                errors.append("{} duplicates {} turn {}".format(prefix, conversation_id, turn_number))
            seen_keys.add(key)
            turns[conversation_id].append(turn_number)

        if row["user_message"] is not None and not isinstance(row["user_message"], str):
            errors.append("{} user_message must be a string or null".format(prefix))
        if row["expected_response_pattern"] is not None and not isinstance(
            row["expected_response_pattern"], str
        ):
            errors.append("{} expected_response_pattern must be a string or null".format(prefix))
        if row["pass_criteria"] not in PASS_CRITERIA:
            errors.append("{} has unsupported pass_criteria".format(prefix))
        if not isinstance(row["category"], str) or not row["category"].strip():
            errors.append("{} category must be a non-empty string".format(prefix))

        calls = row["expected_tool_calls"]
        if not isinstance(calls, list):
            errors.append("{} expected_tool_calls must be a list".format(prefix))
        else:
            for index, call in enumerate(calls):
                if not isinstance(call, dict):
                    errors.append("{} tool call {} must be an object".format(prefix, index))
                    continue
                if not isinstance(call.get("tool"), str) or not call["tool"].strip():
                    errors.append("{} tool call {} has no tool name".format(prefix, index))
                if not isinstance(call.get("params"), dict):
                    errors.append("{} tool call {} params must be an object".format(prefix, index))

        for field in ("requirement_ids", "must_not_call"):
            value = row.get(field, [])
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                errors.append("{} {} must be a list of non-empty strings".format(prefix, field))

        for field in ("expected_response_pattern", "response_must_not_match"):
            pattern = row.get(field)
            if pattern:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append("{} {} is invalid: {}".format(prefix, field, exc))

        if "evaluation_context" in row and not isinstance(row["evaluation_context"], dict):
            errors.append("{} evaluation_context must be an object".format(prefix))

    for conversation_id, numbers in turns.items():
        ordered = sorted(numbers)
        expected = list(range(1, len(ordered) + 1))
        if ordered != expected:
            errors.append(
                "{} has non-sequential turns: {} (expected {})".format(
                    conversation_id, ordered, expected
                )
            )
    return errors, len(rows), len(turns)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="Evaluation JSONL files")
    args = parser.parse_args()

    all_errors = []
    total_rows = 0
    for path in args.files:
        if not path.is_file():
            all_errors.append("{} does not exist or is not a file".format(path))
            continue
        errors, row_count, conversation_count = validate_file(path)
        all_errors.extend(errors)
        total_rows += row_count
        print("{}: {} turns, {} conversations".format(path, row_count, conversation_count))

    if all_errors:
        for error in all_errors:
            print("ERROR: {}".format(error), file=sys.stderr)
        return 1
    print("Validated {} file(s), {} turns".format(len(args.files), total_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
