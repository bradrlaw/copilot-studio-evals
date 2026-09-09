# Baseline Run Records

`banking-agent-baseline-results-template.csv` is a synthetic sample generated from
the designed banking-agent evaluation set. Its expected-behavior columns are
prepopulated; the following columns remain blank until an evaluation is run:

- `Run Date`
- `Run Target`
- `Result`
- `Actual Tools`
- `Actual Response`
- `Notes`

Regenerate the sample template from the repository root:

```powershell
python scripts\generate_baseline_template.py `
  data\eval-sets\eval_scenarios.jsonl `
  data\baseline\banking-agent-baseline-results-template.csv `
  --group-by category
```

After filling the run results, summarize them with:

```powershell
python scripts\summarize_baseline_results.py `
  data\baseline\banking-agent-baseline-results-template.csv
```
