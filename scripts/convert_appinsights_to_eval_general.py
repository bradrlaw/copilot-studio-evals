"""
App Insights -> Eval JSONL Conversion Script (GENERAL / agent-agnostic)
=======================================================================
Generalized variant of convert_appinsights_to_eval.py. It extracts conversations
from Application Insights telemetry and writes the internal eval JSONL format,
WITHOUT any agent-specific tool names or acceptance-criteria logic.

Use this for any Copilot Studio agent. Supply agent-specific tool-name mappings
with --tool-map rather than embedding them in this converter.

Usage:
    # Messages + (optional) tool calls
    python convert_appinsights_to_eval_general.py --messages messages.csv --tools toolcalls.csv --output eval.jsonl

    # Messages only (no separable tool-call log)
    python convert_appinsights_to_eval_general.py --messages messages.csv --output eval.jsonl

    # Optional: normalize raw tool names via a JSON map, and stamp a fixed category
    python convert_appinsights_to_eval_general.py --messages messages.csv --tools toolcalls.csv \
        --tool-map toolmap.json --category "regression" --output eval.jsonl

Inputs:
    --messages  Messages CSV. Two shapes are auto-detected:
                  (a) grouped:  conversationId, events (JSON array), eventCount
                  (b) flat:     timestamp, conversationId, activityType, messageText
    --tools     (optional) Tool-call CSV: "timestamp [UTC]"|timestamp, toolName, outcome, success, duration
    --tool-map  (optional) JSON file mapping raw tool names (lowercased keys) to
                  canonical names, e.g. { "search contacts": "contact.search" }.
                  When omitted, tool names pass through unchanged.
    --category  (optional) Fixed value written to every turn's "category" field.
                  When omitted, a generic structural category is inferred
                  (single-turn | multi-turn | tool-use | multi-turn-tool-use | error).

Output: JSONL, one logical turn per line:
    {conversation_id, turn_number, user_message, expected_tool_calls[],
     expected_response_pattern, pass_criteria, category}
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Tool-name normalization (agent-agnostic)
# ---------------------------------------------------------------------------

def load_tool_map(path: Optional[str]) -> dict:
    """Load an optional {raw_name_lower: canonical_name} mapping from JSON."""
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {str(k).strip().lower(): str(v) for k, v in raw.items()}


def normalize_tool_name(raw_name: str, tool_map: dict) -> Optional[str]:
    """Return the canonical tool name. Passthrough unless a map entry matches."""
    if not raw_name:
        return None
    name = raw_name.strip()
    if tool_map:
        key = name.lower()
        if key in tool_map:
            return tool_map[key]
    return name


def parse_action_input(raw_input: str) -> dict:
    if not raw_input:
        return {}
    try:
        return json.loads(raw_input)
    except (json.JSONDecodeError, TypeError):
        return {"raw": raw_input}


# ---------------------------------------------------------------------------
# Generic structural categorization
# ---------------------------------------------------------------------------

def infer_category(conversation_events: list) -> str:
    """
    Classify a conversation by structural traits only (no domain semantics):
    error | multi-turn-tool-use | tool-use | multi-turn | single-turn
    """
    tool_calls = [e for e in conversation_events if e.get("action")]
    statuses = [e.get("status", "") for e in tool_calls]
    if any(s in ("Failed", "Error") for s in statuses):
        return "error"

    has_tools = len(tool_calls) > 0
    user_turns = sum(
        1 for e in conversation_events
        if e.get("type") == "BotMessageReceived" and e.get("message")
    )

    if has_tools and user_turns > 1:
        return "multi-turn-tool-use"
    if has_tools:
        return "tool-use"
    if user_turns > 1:
        return "multi-turn"
    return "single-turn"


def build_response_pattern(bot_message: str) -> Optional[str]:
    """Build a loose regex from a bot message for expected_response_pattern."""
    if not bot_message:
        return None
    keywords = []
    names = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', bot_message)
    if names:
        keywords.extend(names[:3])
    actions = re.findall(
        r'(?i)\b(logged|created|recorded|found|confirm|linked|updated|added|error|failed)\b',
        bot_message,
    )
    if actions:
        keywords.extend(actions[:2])
    if not keywords:
        return None
    return "(?i)(" + "|".join(re.escape(k) for k in keywords) + ")"


def determine_pass_criteria(turn: dict) -> str:
    has_tool = bool(turn.get("expected_tool_calls"))
    has_pattern = bool(turn.get("expected_response_pattern"))
    if has_tool and has_pattern:
        return "both"
    if has_tool:
        return "tool_called_correctly"
    return "response_matches"


# ---------------------------------------------------------------------------
# Turn grouping
# ---------------------------------------------------------------------------

def group_into_turns(events: list, tool_map: dict) -> list:
    """Group raw events into turns: user message + tool calls + bot response."""
    turns = []
    current = {"turn_number": 1, "user_message": None, "tool_calls": [], "bot_response": None}

    def fresh(n):
        return {"turn_number": n, "user_message": None, "tool_calls": [], "bot_response": None}

    for event in events:
        etype = event.get("type", "")

        if etype == "BotMessageReceived":
            if current["user_message"] is not None:
                turns.append(current)
                current = fresh(current["turn_number"] + 1)
            current["user_message"] = event.get("message", "")

        elif etype in ("ActionExecuted", "FlowActionExecuted", "McpToolCall"):
            tool_name = normalize_tool_name(event.get("action", "") or event.get("toolName", ""), tool_map)
            if tool_name:
                current["tool_calls"].append({
                    "tool": tool_name,
                    "params": parse_action_input(event.get("input", "")),
                    "status": event.get("status", ""),
                    "output": event.get("output", "") or event.get("outcome", ""),
                })

        elif etype in ("BotMessageSent", "BotMessageSend"):
            current["bot_response"] = event.get("message", "")
            turns.append(current)
            current = fresh(current["turn_number"] + 1)

    if current["user_message"] or current["tool_calls"] or current["bot_response"]:
        turns.append(current)

    return [t for t in turns if t["user_message"] or t["bot_response"] or t["tool_calls"]]


def convert_turn_to_eval_line(conversation_id: str, turn: dict, category: str) -> dict:
    expected_tool_calls = [
        {"tool": tc["tool"], "params": tc["params"] if tc["params"] and tc["params"] != {"raw": ""} else {}}
        for tc in turn["tool_calls"]
    ]
    expected_response_pattern = build_response_pattern(turn["bot_response"])
    line = {
        "conversation_id": conversation_id,
        "turn_number": turn["turn_number"],
        "user_message": turn["user_message"],
        "expected_tool_calls": expected_tool_calls,
        "expected_response_pattern": expected_response_pattern,
        "pass_criteria": determine_pass_criteria({
            "expected_tool_calls": expected_tool_calls,
            "expected_response_pattern": expected_response_pattern,
        }),
        "category": category,
    }
    return line


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_messages_csv(filepath: Path) -> list:
    """Load messages CSV - handles grouped (JSON events) and flat formats."""
    conversations = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        if "events" in fieldnames:
            for row in reader:
                conv_id = row.get("conversationId", "").strip()
                if not conv_id:
                    continue
                try:
                    events = json.loads(row.get("events", "[]"))
                except (json.JSONDecodeError, TypeError):
                    continue
                normalized = []
                for e in events:
                    normalized.append({
                        "timestamp": e.get("timestamp", ""),
                        "type": e.get("type", ""),
                        "message": e.get("message", ""),
                        "action": e.get("toolName", ""),
                        "input": "",
                        "output": e.get("outcome", ""),
                        "status": "Success" if str(e.get("success", "true")).lower() == "true" else "Failed",
                    })
                normalized.sort(key=lambda ev: parse_timestamp(ev["timestamp"]) or datetime.min)
                conversations.append({"conversationId": conv_id, "events": normalized})
        else:
            conv_map = {}
            for row in reader:
                conv_id = row.get("conversationId", "").strip()
                if not conv_id:
                    continue
                conv_map.setdefault(conv_id, []).append({
                    "timestamp": row.get("timestamp", ""),
                    "type": row.get("activityType", ""),
                    "message": row.get("messageText", ""),
                    "action": "",
                    "input": "",
                    "output": "",
                    "status": "",
                })
            conversations = [{"conversationId": c, "events": ev} for c, ev in conv_map.items()]

    return conversations


def load_tools_csv(filepath: Path) -> list:
    tools = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = (row.get("timestamp [UTC]", "") or row.get("timestamp", "")).strip()
            tools.append({
                "timestamp": ts,
                "toolName": row.get("toolName", "").strip(),
                "outcome": row.get("outcome", "").strip(),
                "success": row.get("success", "True").strip(),
                "duration": row.get("duration", "0").strip(),
            })
    return tools


def parse_timestamp(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    ts_clean = re.sub(r'(\.\d{6})\d+', r'\1', ts)
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y, %I:%M:%S.%f %p",
        "%m/%d/%Y, %I:%M:%S %p",
    ]:
        try:
            return datetime.strptime(ts_clean, fmt)
        except ValueError:
            continue
    return None


def correlate_tools_to_conversations(conversations: list, tools: list) -> list:
    """Attribute each tool call to the narrowest conversation time window."""
    conv_windows = []
    for conv in conversations:
        timestamps = [parse_timestamp(e["timestamp"]) for e in conv["events"]]
        timestamps = [t for t in timestamps if t]
        if timestamps:
            conv_windows.append({
                "conversationId": conv["conversationId"],
                "minTime": min(timestamps),
                "maxTime": max(timestamps),
                "span": max(timestamps) - min(timestamps),
            })

    parsed_tools = []
    for tool in tools:
        ts = parse_timestamp(tool["timestamp"])
        if ts:
            parsed_tools.append({**tool, "_ts": ts})
    parsed_tools.sort(key=lambda x: x["_ts"])

    buffer = timedelta(seconds=30)
    assignments = {}
    for tool in parsed_tools:
        best, best_span = None, None
        for w in conv_windows:
            if (w["minTime"] - buffer) <= tool["_ts"] <= (w["maxTime"] + buffer):
                if best is None or w["span"] < best_span:
                    best, best_span = w["conversationId"], w["span"]
        if best:
            assignments.setdefault(best, []).append(tool)

    for conv in conversations:
        cid = conv["conversationId"]
        if cid in assignments:
            for tool in assignments[cid]:
                conv["events"].append({
                    "timestamp": tool["_ts"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "type": "McpToolCall",
                    "message": "",
                    "action": tool["toolName"],
                    "input": "",
                    "output": tool.get("outcome", ""),
                    "status": "Success" if tool.get("success", "True") == "True" else "Failed",
                })
            conv["events"].sort(key=lambda e: parse_timestamp(e["timestamp"]) or datetime.min)

    return conversations


def make_conversation_id(raw_id: str, index: int, prefix: str) -> str:
    short = raw_id[:8] if len(raw_id) > 8 else raw_id
    return f"{prefix}-{index:03d}-{short}"


def convert_conversations(conversations: list, tool_map: dict, fixed_category: Optional[str], prefix: str) -> list:
    all_lines = []
    for idx, conv in enumerate(conversations, start=1):
        events = conv["events"]
        if not events:
            continue
        turns = group_into_turns(events, tool_map)
        if not turns:
            continue
        category = fixed_category if fixed_category else infer_category(events)
        conv_id = make_conversation_id(conv["conversationId"], idx, prefix)
        for i, turn in enumerate(turns, start=1):
            turn["turn_number"] = i
            all_lines.append(convert_turn_to_eval_line(conv_id, turn, category))
    return all_lines


def write_jsonl(lines: list, output_path: Path):
    with open(output_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def print_summary(lines: list, conversations: list):
    conv_ids = {l["conversation_id"] for l in lines}
    tools_used = set()
    cats = {}
    for l in lines:
        for tc in l.get("expected_tool_calls", []):
            tools_used.add(tc["tool"])
        c = l.get("category", "")
        cats[c] = cats.get(c, 0) + 1
    print("\n" + "=" * 60)
    print("CONVERSION SUMMARY")
    print("=" * 60)
    print(f"  Input conversations:  {len(conversations)}")
    print(f"  Output conversations: {len(conv_ids)}")
    print(f"  Total eval turns:     {len(lines)}")
    print(f"  Distinct tools:       {len(tools_used)}")
    if tools_used:
        for t in sorted(tools_used):
            print(f"    - {t}")
    print("  Categories:")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    - {c or '(none)'}: {n} turns")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Convert App Insights conversation export to eval JSONL (agent-agnostic)"
    )
    parser.add_argument("--messages", "-m", help="Messages CSV (grouped or flat)")
    parser.add_argument("--tools", "-t", help="Optional tool-call CSV")
    parser.add_argument("--input", "-i", help="Alias for --messages (messages only)")
    parser.add_argument("--tool-map", help="Optional JSON map of raw->canonical tool names")
    parser.add_argument("--category", help="Fixed category value for every turn (else inferred)")
    parser.add_argument("--output", "-o", default="eval.jsonl", help="Output JSONL path")
    parser.add_argument("--prefix", default="conv", help="Prefix for generated conversation IDs")
    parser.add_argument("--min-turns", type=int, default=1, help="Minimum turns to keep a conversation")
    args = parser.parse_args()

    messages_arg = args.messages or args.input
    if not messages_arg:
        print("Error: provide --messages (or --input).")
        sys.exit(1)

    messages_path = Path(messages_arg)
    if not messages_path.exists():
        print(f"Error: messages file not found: {messages_path}")
        sys.exit(1)

    tool_map = load_tool_map(args.tool_map)

    print(f"Loading messages from: {messages_path}")
    conversations = load_messages_csv(messages_path)
    print(f"  Found {len(conversations)} conversations")

    if args.tools:
        tools_path = Path(args.tools)
        if not tools_path.exists():
            print(f"Error: tools file not found: {tools_path}")
            sys.exit(1)
        print(f"Loading tool calls from: {tools_path}")
        tools = load_tools_csv(tools_path)
        print(f"  Found {len(tools)} tool-call records")
        conversations = correlate_tools_to_conversations(conversations, tools)
        correlated = sum(1 for c in conversations if any(e.get("type") == "McpToolCall" for e in c["events"]))
        print(f"  Correlated tools to {correlated} conversations")
    else:
        print("  No --tools provided; conversations will have no tool-call data")

    filtered = [c for c in conversations if len(group_into_turns(c["events"], tool_map)) >= args.min_turns]
    print(f"  After min-turns filter ({args.min_turns}): {len(filtered)} conversations")

    lines = convert_conversations(filtered, tool_map, args.category, args.prefix)
    write_jsonl(lines, Path(args.output))
    print(f"\nOutput written to: {args.output}")
    print_summary(lines, filtered)


if __name__ == "__main__":
    main()
