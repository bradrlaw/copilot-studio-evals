# Synthetic Banking Agent Source Artifacts

These files are fictional design inputs for demonstrating how to build Copilot
Studio evaluations. They do not describe a real bank, customer, environment, or
deployed agent.

## Files

| File | Purpose |
| --- | --- |
| `banking-agent-miro-flow.csv` | Node-and-edge representation of common banking conversation flows for import or reconstruction in Miro |
| `banking-agent-acceptance-criteria.csv` | Traceable Given/When/Then acceptance criteria used to derive evaluation scenarios |
| `banking-agent-flow.jpg` | High-resolution visual overview generated from the flow CSV |

## Miro flow format

The flow CSV contains both nodes and connectors:

- `record_type`: `node` or `edge`.
- `id`: unique node or edge identifier.
- `flow_id` and `flow_name`: group related flows.
- `lane`: `User`, `Agent`, or `System`.
- `shape`: suggested Miro shape for nodes.
- `text`: visible node text.
- `from_id`, `to_id`, and `connector_label`: connector definition.
- `expected_tool`: canonical tool associated with the node or edge.
- `acceptance_criteria_ids`: semicolon-separated traceability.

Miro import capabilities vary by plan and application version. If direct diagram
import is unavailable, import the CSV as a table or cards and use `from_id` and
`to_id` to reconstruct connectors.

## Example agent scope

The synthetic banking agent supports:

- balance inquiries;
- recent transaction searches;
- transfers between the user's own accounts;
- payments to saved payees;
- card lock and unlock;
- transaction-dispute intake;
- conversation reset and safe recovery.

The example deliberately excludes credential collection, external transfers,
new-payee enrollment, lending decisions, personalized financial advice, and
guaranteed dispute outcomes.

All expected tool names are illustrative and should be replaced with the actual
names emitted by the agent under test.

Regenerate the JPG after changing the flow CSV:

```powershell
python scripts\generate_banking_flow_image.py
```

Generate the deterministic sample evaluation sets from the two CSV source files:

```powershell
python scripts\generate_banking_sample_evals.py
```

The generated `data\eval-sets\eval_from_real.jsonl` file contains entirely
fictional, synthetic observed-style conversations for pipeline compatibility.
It is not telemetry and contains no real customer data.
