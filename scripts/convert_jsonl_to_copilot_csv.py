"""
Eval JSONL -> Copilot Studio Evaluation CSV Conversion Script
=============================================================
Converts the internal eval JSONL format into the CSV format consumed by the
Copilot Studio built-in evaluation tool ("Import conversations to test your
agent").

Usage:
    python convert_jsonl_to_copilot_csv.py <input.jsonl> <output.csv>

    # Examples
    python convert_jsonl_to_copilot_csv.py eval_scenarios.jsonl eval_scenarios_copilot.csv
    python convert_jsonl_to_copilot_csv.py eval_from_real.jsonl eval_from_real_copilot.csv

Input JSONL line schema (one logical turn per line):
    {conversation_id, turn_number, user_message, expected_tool_calls[],
     expected_response_pattern, pass_criteria, category}

Output CSV columns (Copilot Studio template):
    conversationNumber, question, response

Copilot Studio import limits (enforced here):
    - 20 conversations max per file (larger sets are split into _partN files)
    - 6 question-and-answer pairs (turns) max per conversation
    - 500 characters max per question

Notes:
    - The 'response' column is an OPTIONAL reference answer. The Copilot Studio
      evaluation tool does NOT compare the agent's reply against it, so it is
      left blank by default. Pass --with-reference to emit the captured
      expected_response_pattern instead.
    - Conversations are prioritized so the most valuable cases survive the
      import cap: those that exercise tool calls first, then those with the most
      user turns.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# Copilot Studio evaluation import limits (per file)
MAX_CONVERSATIONS = 20
MAX_TURNS_PER_CONVERSATION = 6
MAX_QUESTION_CHARS = 500


def load_jsonl(path: Path) -> list:
    """Load eval JSONL lines."""
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            lines.append(json.loads(raw))
    return lines


def group_by_conversation(lines: list) -> dict:
    """Group turns by conversation_id, preserving turn order."""
    conversations = {}
    for line in lines:
        # Fall back to query_id for single-turn datasets (e.g. the search
        # latency set) that use a flat query schema instead of conversation_id.
        cid = line.get("conversation_id") or line.get("query_id", "")
        conversations.setdefault(cid, []).append(line)
    # Sort each conversation's turns by turn_number for deterministic ordering
    for cid in conversations:
        conversations[cid].sort(key=lambda t: t.get("turn_number", 0))
    return conversations


def conversation_priority(item: tuple) -> tuple:
    """
    Sort key to keep the most valuable conversations in the earliest chunks.
    Priority: (has tool calls, number of user turns).
    """
    _cid, turns = item
    has_tools = any(t.get("expected_tool_calls") for t in turns)
    user_turn_count = sum(1 for t in turns if t.get("user_message"))
    return (has_tools, user_turn_count)


def convert(
    lines: list,
    max_turns: int = MAX_TURNS_PER_CONVERSATION,
    max_chars: int = MAX_QUESTION_CHARS,
    with_reference: bool = False,
) -> list:
    """
    Convert eval JSONL lines into a prioritized list of conversations.

    Returns a list of conversations, each a list of (question, response) tuples.
    Conversations are ordered by priority (tool-call cases first, then longer
    ones) so that chunking keeps the most valuable cases in the earliest files.
    No conversations are dropped here — capping/splitting happens at write time.
    Conversations longer than max_turns are truncated to their first max_turns
    user turns to satisfy the per-conversation limit while preserving context.
    """
    conversations = group_by_conversation(lines)

    # Keep only conversations that have at least one user message
    candidates = [
        (cid, turns)
        for cid, turns in conversations.items()
        if any(t.get("user_message") for t in turns)
    ]

    # Prioritize the most valuable conversations first
    candidates.sort(key=conversation_priority, reverse=True)

    result = []
    truncated = 0
    for _cid, turns in candidates:
        user_turns = [t for t in turns if t.get("user_message")]
        if len(user_turns) > max_turns:
            truncated += 1
        user_turns = user_turns[:max_turns]
        conv = []
        for turn in user_turns:
            question = (turn.get("user_message") or "")[:max_chars]
            response = (turn.get("expected_response_pattern") or "") if with_reference else ""
            conv.append((question, response))
        result.append(conv)

    return result, truncated


def chunk_output_paths(output: Path, num_chunks: int) -> list:
    """Return the output path(s). A single chunk keeps the given name; multiple
    chunks get a _partN suffix inserted before the extension."""
    if num_chunks <= 1:
        return [output]
    return [
        output.with_name(f"{output.stem}_part{i}{output.suffix}")
        for i in range(1, num_chunks + 1)
    ]


def write_chunks(
    conversations: list,
    output: Path,
    chunk_size: int = MAX_CONVERSATIONS,
) -> list:
    """Split conversations into files of at most chunk_size conversations each.

    conversationNumber restarts at 1 within every file (each file is imported
    independently). Returns a list of (path, conv_count, turn_count).
    """
    chunks = [
        conversations[i : i + chunk_size]
        for i in range(0, len(conversations), chunk_size)
    ] or [[]]
    paths = chunk_output_paths(output, len(chunks))

    written = []
    for path, chunk in zip(paths, chunks):
        rows = []
        for conv_num, conv in enumerate(chunk, start=1):
            for question, response in conv:
                rows.append((conv_num, question, response))
        write_csv(rows, path)
        written.append((path, len(chunk), len(rows)))
    return written


def write_csv(rows: list, path: Path):
    """Write rows to CSV with the Copilot Studio header (UTF-8 BOM)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["conversationNumber", "question", "response"])
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="Convert eval JSONL to Copilot Studio evaluation CSV format"
    )
    parser.add_argument("input", help="Input eval JSONL file")
    parser.add_argument("output", help="Output Copilot Studio CSV file")
    parser.add_argument(
        "--with-reference",
        action="store_true",
        help="Emit expected_response_pattern in the optional 'response' column "
             "(default: leave blank, since the eval tool ignores it)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=MAX_CONVERSATIONS,
        help=f"Max conversations per output file; larger sets are split into "
             f"_partN files (default: {MAX_CONVERSATIONS})",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=MAX_TURNS_PER_CONVERSATION,
        help=f"Max question-answer pairs per conversation (default: {MAX_TURNS_PER_CONVERSATION})",
    )
    parser.add_argument(
        "--split-by",
        metavar="FIELD",
        help="Write one file per distinct value of FIELD (taken from each line), "
             "e.g. --split-by tool produces a separate CSV per tool. The value is "
             "appended to the output stem. Useful for isolating one tool's calls "
             "into a single import run (and therefore a single App Insights time "
             "window).",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        sys.exit(1)

    lines = load_jsonl(input_path)

    if args.split_by:
        _run_split(lines, args)
        return

    conversations, truncated = convert(
        lines,
        max_turns=args.max_turns,
        with_reference=args.with_reference,
    )
    written = write_chunks(conversations, Path(args.output), chunk_size=args.chunk_size)

    total_conversations = len(group_by_conversation(lines))
    total_turns = sum(t for _p, _c, t in written)
    print(f"Input:  {input_path}  ({len(lines)} turns, {total_conversations} conversations)")
    print(f"Output: {len(written)} file(s), {len(conversations)} conversations, {total_turns} turns")
    for path, conv_count, turn_count in written:
        print(f"  - {path}  ({conv_count} conversations, {turn_count} turns)")
    if truncated:
        print(
            f"Note: {truncated} conversation(s) exceeded {args.max_turns} turns "
            "and were truncated to their first turns."
        )


def _sanitize(value: str) -> str:
    """Make a field value safe for a filename stem (e.g. contact.search -> contact_search)."""
    return "".join(c if c.isalnum() else "_" for c in str(value)).strip("_")


def _run_split(lines: list, args) -> None:
    """Write one output file (set) per distinct value of args.split_by.

    Preserves input order of values so files are produced deterministically.
    Each group is still capped/split at chunk-size like the default path.
    """
    output = Path(args.output)
    groups = {}
    for line in lines:
        key = line.get(args.split_by, "")
        groups.setdefault(key, []).append(line)

    print(f"Input:  {Path(args.input)}  ({len(lines)} turns, split by '{args.split_by}' "
          f"into {len(groups)} value(s))")
    for value, group_lines in groups.items():
        conversations, _truncated = convert(
            group_lines,
            max_turns=args.max_turns,
            with_reference=args.with_reference,
        )
        group_output = output.with_name(f"{output.stem}_{_sanitize(value)}{output.suffix}")
        written = write_chunks(conversations, group_output, chunk_size=args.chunk_size)
        for path, conv_count, turn_count in written:
            print(f"  - [{value}] {path}  ({conv_count} conversations, {turn_count} turns)")


if __name__ == "__main__":
    main()
