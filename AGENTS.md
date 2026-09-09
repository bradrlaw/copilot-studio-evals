# Copilot Studio Evaluation Framework - Agent Guidance

## Project purpose

This project is an agent-agnostic framework for designing, preparing, running, and
analyzing Microsoft Copilot Studio evaluations. The evaluated system is called the
**agent under test**.

Read these documents before making substantial changes:

- `README.md` - project entry point and quick start.
- `process.md` - end-to-end evaluation lifecycle.
- `architecture.md` - design, boundaries, data contracts, and roadmap.

## Core workflow

1. Build designed scenarios from UX flows, requirements, tool contracts, risks, and
   failure modes.
2. Optionally derive cases from governed Application Insights telemetry.
3. Normalize both sources to canonical JSONL.
4. Review expectations, coverage, traceability, privacy, and tool mappings.
5. Generate import files for Copilot Studio Evaluation and/or Copilot Studio Kit.
6. Run against a versioned agent and export the results.
7. Classify failures, compare with the baseline, and add regression coverage.

## Environment

- CPython 3.11 through 3.14; see `docs\python-support-policy.md`.
- Core conversion and baseline scripts use the standard library.
- Optional image and PowerPoint helpers use `requirements-optional.txt`.
- There is no build step.
- On Windows, use backslash paths. Close generated CSVs in Excel before overwriting
  them.

## Supported generic entry points

```powershell
# Application Insights exports -> canonical JSONL
python scripts\convert_appinsights_to_eval_general.py `
  --messages <messages.csv> --tools <toolcalls.csv> `
  --output data\eval-sets\eval.jsonl

# Validate JSONL before generating runner-specific files
python scripts\validate_eval_jsonl.py data\eval-sets\eval.jsonl

# JSONL -> runner formats
python scripts\convert_jsonl_to_copilot_csv.py `
  data\eval-sets\eval.jsonl data\generated\eval_copilot.csv

python scripts\convert_jsonl_to_kit_csv.py `
  data\eval-sets\eval.jsonl data\generated\eval_kit.csv `
  --test-set "Agent regression"

# Baseline record and summary
python scripts\generate_baseline_template.py `
  data\eval-sets\eval.jsonl data\baseline\results.csv

python scripts\summarize_baseline_results.py data\baseline\results.csv
```

## Canonical JSONL

Each line represents one logical conversation turn. Core fields are
`conversation_id`, `turn_number`, `user_message`, `expected_tool_calls`,
`expected_response_pattern`, `pass_criteria`, and `category`. Optional negative
assertions include `must_not_call` and `response_must_not_match`.

Expected tools and parameters must be reconciled with the deployed agent version.
Do not copy tool mappings or expected behavior from an unrelated agent.

## Privacy and publication

- Raw telemetry, telemetry-derived conversations, Office source artifacts, and
  internal reports are private by default.
- A UAT or synthetic label is not sufficient evidence that an artifact is safe to
  publish.
- Public examples must be created independently with fictional entities, reserved
  domains, placeholder IDs, and illustrative metrics.
- Never commit tokens, tenant IDs, application IDs, environment IDs, client data, or
  production transcripts.
- Reports should use aggregates and synthetic excerpts.
- Review every customized dataset and generated report before publication; the
  committed banking artifacts are synthetic framework examples.

## Design conventions

- Keep agent-specific mappings and telemetry schemas in configuration or adapters,
  not generic converters.
- Keep canonical JSONL independent from runner-specific CSV limits.
- Treat source KQL and workbook generator scripts as authoritative; regenerate
  workbook JSON after query changes.
- Preserve the distinction between exact conversation correlation and approximate
  timestamp correlation.
- Record agent version, environment, dataset version, evaluator configuration, and
  run date with every baseline.
- Use behavior-based response assertions instead of brittle exact prose.
- Keep expected-result changes reviewable separately from agent changes.
- Comment code only when the logic is not self-explanatory.

## Current enhancement priorities

1. Add automated converter, correlation, validator, and privacy tests.
2. Make telemetry field mappings and pricing data externally configurable.
3. Add generated-workbook consistency checks.
4. Add run metadata manifests and normalized result ingestion.
5. Add repository automation before making the GitHub repository public.
