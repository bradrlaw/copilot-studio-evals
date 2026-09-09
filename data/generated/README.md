# Generated Banking Evaluation Files

These files are generated from the fully synthetic banking-agent JSONL datasets:

- `eval_scenarios_*` comes from designed scenarios derived from the source flows
  and acceptance criteria.
- `eval_from_real_*` comes from fictional observed-style conversations. Despite
  the compatibility filename, it contains no real telemetry or customer data.

Regenerate the source JSONL and all import files from the repository root:

```powershell
python scripts\generate_banking_sample_evals.py

python scripts\convert_jsonl_to_copilot_csv.py `
  data\eval-sets\eval_scenarios.jsonl `
  data\generated\eval_scenarios_copilot.csv

python scripts\convert_jsonl_to_copilot_csv.py `
  data\eval-sets\eval_from_real.jsonl `
  data\generated\eval_from_real_copilot.csv

python scripts\convert_jsonl_to_kit_csv.py `
  data\eval-sets\eval_scenarios.jsonl `
  data\generated\eval_scenarios_kit.csv `
  --test-set "Sample Banking Agent - Designed scenarios"

python scripts\convert_jsonl_to_kit_csv.py `
  data\eval-sets\eval_from_real.jsonl `
  data\generated\eval_from_real_kit.csv `
  --test-set "Sample Banking Agent - Synthetic observed patterns"
```

Copilot Studio conversational imports are split into `_partN` files when the
dataset exceeds the per-file conversation limit. The commands above therefore
produce the committed `eval_scenarios_copilot_part1.csv`,
`eval_scenarios_copilot_part2.csv`, `eval_from_real_copilot_part1.csv`, and
`eval_from_real_copilot_part2.csv` rather than unsuffixed Copilot CSV files.
