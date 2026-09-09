# Report Templates

This directory contains editable, agent-agnostic PowerPoint templates:

| Template | Purpose |
| --- | --- |
| `baseline-evaluation-report-template.pptx` | Evaluation scope, coverage, results, failure analysis, actions, decision, and run metadata |
| `observability-walkthrough-template.pptx` | Telemetry architecture, dashboard tour, troubleshooting, limitations, operational response, and rollout |

All template content is synthetic and uses `<PLACEHOLDER>` values. Do not copy
production transcripts, client data, environment identifiers, or secrets into a
report intended for public distribution.

Regenerate both templates with:

```powershell
python scripts\generate_report_templates.py
```

The generator sets generic document metadata and creates the decks from scratch so
they do not inherit embedded screenshots, notes, or properties from prior reports.

## Using the templates

1. Make a copy of the relevant template for a specific agent and run.
2. Replace every `<PLACEHOLDER>`.
3. Use aggregate metrics and normalized failure categories.
4. Use synthetic excerpts unless transcript disclosure is explicitly approved.
5. Record the agent version, environment, dataset version, evaluator configuration,
   run ID, date, owner, and limitations.
6. Check document properties, speaker notes, hyperlinks, and images before sharing.
