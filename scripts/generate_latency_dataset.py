#!/usr/bin/env python3
"""Generate a synthetic banking-agent tool-latency evaluation dataset."""

import argparse
import csv
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_OUTDIR = HERE.parent / "data" / "latency"

# Illustrative targets for the sample agent, not measured service-level objectives.
TOOL_LATENCY = {
    "account.balance": {"expected_ms": 2000, "requirement_ids": ["AC-008"]},
    "transaction.search": {"expected_ms": 3000, "requirement_ids": ["AC-010", "AC-011"]},
    "payee.search": {"expected_ms": 2000, "requirement_ids": ["AC-021"]},
    "card.list": {"expected_ms": 2000, "requirement_ids": ["AC-025"]},
    "transfer.validate": {"expected_ms": 2500, "requirement_ids": ["AC-014", "AC-015"]},
    "payment.validate": {"expected_ms": 2500, "requirement_ids": ["AC-022"]},
}

QUERIES = {
    "account.balance": [
        "What is available in checking ending 4821?",
        "Show the current balance for savings ending 7304.",
        "How much can I spend from checking ending 2208?",
        "Balance for my goal savings ending 6815.",
        "Check the available balance in daily checking ending 2208.",
        "What is in reserve savings ending 7304?",
        "Show current and available balances for checking ending 4821.",
        "How much is available in savings ending 6815?",
        "Check my travel savings account ending 3360.",
        "What is the balance of household checking ending 5544?",
        "Show the balance for emergency savings ending 9082.",
        "Available funds in checking ending 7715?",
    ],
    "transaction.search": [
        "Find coffee purchases from the last seven days in checking ending 4821.",
        "Show posted grocery transactions this month in checking ending 2208.",
        "Find pending charges over $25 in checking ending 5544.",
        "Show ATM withdrawals from last month in checking ending 7715.",
        "Find transactions from Example Market in the last 30 days.",
        "Show deposits over $100 in savings ending 7304.",
        "Find the five most recent posted transactions in checking ending 2208.",
        "Search for a $42.15 charge from Sample Fuel.",
        "Show subscriptions charged this month in checking ending 4821.",
        "Find restaurant purchases between September 1 and September 7.",
        "Show pending card transactions on checking ending 5544.",
        "Find transfers into goal savings ending 6815 this week.",
    ],
    "payee.search": [
        "Find my saved payee named Example Electric.",
        "Look up the saved Sample Wireless payee.",
        "Find a saved payee matching Metro Water.",
        "Search saved payees for Sample Internet.",
        "Look up Example Rent in my saved payees.",
        "Find the saved Sample Gym payee.",
        "Search for Example Insurance in saved payees.",
        "Find my saved payee called Sample Cable.",
    ],
    "card.list": [
        "Show my cards so I can choose one to lock.",
        "List the cards eligible for a status change.",
        "Which debit cards can I lock?",
        "Show my masked credit card choices.",
        "List active cards associated with my profile.",
        "Which card ends in 1780?",
        "Show debit and credit cards using masked labels.",
        "Find the card ending 6033.",
    ],
    "transfer.validate": [
        "Validate a $25 transfer from checking ending 4821 to savings ending 7304.",
        "Check whether I can move $80 from checking ending 2208 to savings ending 6815.",
        "Validate a $10 transfer between checking ending 5544 and savings ending 9082.",
        "Check a $125 transfer from checking ending 7715 to savings ending 3360 tomorrow.",
        "Validate a $40 transfer from savings ending 7304 to checking ending 4821.",
    ],
    "payment.validate": [
        "Validate a $65 payment to Example Electric tomorrow from checking ending 4821.",
        "Check a $72.15 payment to Sample Wireless next Tuesday.",
        "Validate a $950 payment to Example Rent on the first of next month.",
        "Check a $33 payment to Sample Gym from checking ending 2208.",
        "Validate a $48 payment to Sample Internet from checking ending 5544.",
    ],
}

TOOL_PREFIX = {
    "account.balance": "account-balance",
    "transaction.search": "transaction-search",
    "payee.search": "payee-search",
    "card.list": "card-list",
    "transfer.validate": "transfer-validate",
    "payment.validate": "payment-validate",
}

CSV_FIELDS = [
    "query_id",
    "tool",
    "user_message",
    "expected_latency_ms",
    "baseline_p95_ms",
    "category",
    "requirement_ids",
    "source",
]


def build_rows():
    rows = []
    for tool_name, queries in QUERIES.items():
        config = TOOL_LATENCY[tool_name]
        for index, message in enumerate(queries, start=1):
            rows.append(
                {
                    "query_id": "bank-lat-{}-{:03d}".format(TOOL_PREFIX[tool_name], index),
                    "conversation_id": "bank-lat-{}-{:03d}".format(
                        TOOL_PREFIX[tool_name], index
                    ),
                    "turn_number": 1,
                    "tool": tool_name,
                    "user_message": message,
                    "expected_tool_calls": [{"tool": tool_name, "params": {}}],
                    "expected_response_pattern": None,
                    "pass_criteria": "tool_called_correctly",
                    "expected_latency_ms": config["expected_ms"],
                    "baseline_p95_ms": None,
                    "category": "banking-tool-latency",
                    "requirement_ids": config["requirement_ids"],
                    "source": "synthetic",
                    "must_not_call": [],
                    "response_must_not_match": None,
                    "evaluation_context": {},
                }
            )
    return rows


def validate(rows):
    expected_count = sum(len(messages) for messages in QUERIES.values())
    if len(rows) != expected_count:
        raise ValueError("Expected {} rows, found {}".format(expected_count, len(rows)))
    identifiers = [row["query_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate query IDs")
    for row in rows:
        if row["tool"] not in TOOL_LATENCY:
            raise ValueError("Unknown tool: {}".format(row["tool"]))
        if row["source"] != "synthetic":
            raise ValueError("Latency fixtures must be synthetic")


def write_jsonl(rows, path):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n")


def write_csv(rows, path):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field) for field in CSV_FIELDS}
            output["baseline_p95_ms"] = ""
            output["requirement_ids"] = ";".join(row["requirement_ids"])
            writer.writerow(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outdir", nargs="?", type=Path, default=DEFAULT_OUTDIR)
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    validate(rows)
    jsonl_path = args.outdir / "banking_latency_eval.jsonl"
    csv_path = args.outdir / "banking_latency_eval.csv"
    write_jsonl(rows, jsonl_path)
    write_csv(rows, csv_path)

    print("Wrote {} synthetic banking latency queries".format(len(rows)))
    for tool_name in TOOL_LATENCY:
        count = sum(1 for row in rows if row["tool"] == tool_name)
        print("  {:20} {:2}  expected <= {} ms".format(
            tool_name, count, TOOL_LATENCY[tool_name]["expected_ms"]
        ))
    print("  -> {}".format(jsonl_path))
    print("  -> {}".format(csv_path))


if __name__ == "__main__":
    main()
