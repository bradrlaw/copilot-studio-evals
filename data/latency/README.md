# Banking Agent Latency Evaluation Example

This directory contains a fully synthetic 50-query latency benchmark for the
sample banking agent. It demonstrates how to drive repeatable Copilot Studio tool
calls and measure isolated tool latency from Application Insights.

The included thresholds are **illustrative**, not measured service-level
objectives. Replace them with approved targets or a measured baseline when
adapting the dataset to another agent.

## Tools and distribution

| Tool | Queries | Illustrative p95 threshold |
| --- | ---: | ---: |
| `account.balance` | 12 | 2000 ms |
| `transaction.search` | 12 | 3000 ms |
| `payee.search` | 8 | 2000 ms |
| `card.list` | 8 | 2000 ms |
| `transfer.validate` | 5 | 2500 ms |
| `payment.validate` | 5 | 2500 ms |

Only read and validation operations are included. The latency suite does not
create transfers, payments, disputes, or card-status changes.

## Files

| File | Purpose |
| --- | --- |
| `banking_latency_eval.jsonl` | Primary synthetic latency dataset |
| `banking_latency_eval.csv` | Spreadsheet-friendly copy |
| `banking_latency_copilot_<tool>.csv` | Copilot Studio imports split by tool |
| `running-latency-evals.md` | Run and measurement procedure |

## Regenerate

From the repository root:

```powershell
python scripts\generate_latency_dataset.py

python scripts\convert_jsonl_to_copilot_csv.py `
  data\latency\banking_latency_eval.jsonl `
  data\latency\banking_latency_copilot.csv `
  --split-by tool
```

Follow [running-latency-evals.md](running-latency-evals.md) to execute each tool
file in its own time window and compare measured p95 latency with the target.
