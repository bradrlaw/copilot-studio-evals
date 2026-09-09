#!/usr/bin/env python3
"""Summarize a filled-in baseline results template into benchmark numbers.

Reads the CSV produced by generate_baseline_template.py (after the tester has filled the
`Result` column with PASS / FAIL / BLOCKED) and prints pass rates overall and per
group (category by default), plus a list of failures.

By default it rolls up by the full `category` value. Use `--group-by` and
`--group-split` for another traceability field or hierarchical grouping.

Usage:
    python summarize_baseline_results.py baseline_results_template.csv
    python summarize_baseline_results.py results.csv --group-by category --group-split ""
"""
import argparse
import csv
import collections


def norm(v):
    return (v or "").strip().upper()


def main():
    ap = argparse.ArgumentParser(description="Summarize baseline results")
    ap.add_argument("input", help="Filled-in baseline results CSV")
    ap.add_argument("--group-by", default="category",
                    help="Column to roll up by (default: category)")
    ap.add_argument("--group-split", default="",
                    help="Roll up by the substring before the first occurrence of this "
                         "string; pass an empty string to use the full value (default: '')")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    by_result = collections.Counter(norm(r.get("Result")) for r in rows)
    graded = by_result.get("PASS", 0) + by_result.get("FAIL", 0)

    def group_key(r):
        val = (r.get(args.group_by) or "").strip()
        if args.group_split:
            val = val.split(args.group_split)[0]
        return val or "(untagged)"

    by_group = collections.defaultdict(collections.Counter)
    for r in rows:
        by_group[group_key(r)][norm(r.get("Result"))] += 1

    print("=" * 60)
    print(f"BASELINE SNAPSHOT — {args.input}")
    print("=" * 60)
    print(f"Total turns:      {total}")
    print(f"  PASS:    {by_result.get('PASS', 0)}")
    print(f"  FAIL:    {by_result.get('FAIL', 0)}")
    print(f"  BLOCKED: {by_result.get('BLOCKED', 0)}")
    unrec = total - graded - by_result.get("BLOCKED", 0)
    print(f"  (not yet recorded: {unrec})")
    if graded:
        print(f"\nPass rate (of graded PASS+FAIL): {by_result.get('PASS', 0) / graded:.0%}")

    width = max([12] + [len(k) + 2 for k in by_group])
    print(f"\nBy {args.group_by}:")
    print(f"  {'group':<{width}}{'PASS':>6}{'FAIL':>6}{'BLOCK':>7}{'rate':>8}")
    for key in sorted(by_group):
        c = by_group[key]
        g = c.get("PASS", 0) + c.get("FAIL", 0)
        rate = f"{c.get('PASS', 0) / g:.0%}" if g else "-"
        print(f"  {key:<{width}}{c.get('PASS', 0):>6}{c.get('FAIL', 0):>6}{c.get('BLOCKED', 0):>7}{rate:>8}")

    failures = [r for r in rows if norm(r.get("Result")) == "FAIL"]
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for r in failures:
            note = (r.get("Notes") or "").strip()
            note = f" — {note}" if note else ""
            print(f"  [{r.get(args.group_by, '')}] "
                  f"{r.get('conversation_id','')} turn {r.get('turn_number','')}{note}")


if __name__ == "__main__":
    main()
