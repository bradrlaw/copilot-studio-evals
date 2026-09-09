# Publication Readiness Checklist

The committed banking datasets, flow image, generated imports, baseline template,
latency fixtures, and PowerPoint templates are synthetic examples. This checklist
applies when publishing the toolkit or a customized implementation.

## Data and privacy

- Confirm every committed example is independently synthetic.
- Exclude raw telemetry, production transcripts, user identifiers, environment IDs,
  tenant IDs, application IDs, secrets, and internal URLs.
- Use reserved domains such as `example.test` and fictional organizations.
- Review Office document properties, speaker notes, hyperlinks, and embedded images.
- Publish aggregate telemetry findings rather than sensitive transcript excerpts.

## Evaluation integrity

- Validate canonical JSONL:

  ```powershell
  python scripts\validate_eval_jsonl.py <evaluation.jsonl>
  ```

- Reconcile expected tool names and parameters with the deployed agent version.
- Confirm requirement, capability, risk, and negative-test coverage.
- Distinguish designed scenarios from synthetic observed-style examples and governed
  real telemetry.
- Record the agent version, dataset version, evaluator configuration, and run date.

## Reproducibility

- Regenerate evaluation sets, runner CSVs, baseline templates, latency fixtures,
  flow images, PowerPoint templates, and Azure Workbooks from their source files.
- Confirm generated row counts and chunk names match documentation.
- Keep source KQL and Python builders authoritative over generated workbook JSON.
- Remove compiled Python files and temporary exports.

## Dependencies and configuration

- Install optional packages only when needed:

  ```powershell
  python -m pip install -r requirements-optional.txt
  ```

- Copy and customize the examples under `config/`.
- Supply authentication and environment identifiers at runtime.
- Never commit filled secret-bearing configuration files.

## Public project governance

The repository includes the Microsoft open-source governance baseline:

- [`LICENSE`](../LICENSE) - MIT License with Microsoft Corporation copyright.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) - contribution workflow, Microsoft CLA
  requirements, privacy expectations, and validation guidance.
- [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) - Microsoft Open Source Code of
  Conduct adoption and reporting channels.
- [`SECURITY.md`](../SECURITY.md) - Microsoft security vulnerability reporting
  guidance.
- [`SUPPORT.md`](../SUPPORT.md) - best-effort community and maintainer support
  with no Microsoft Customer Service & Support commitment or SLA.

Before creating the public repository, also:

- confirm the project has completed the required Microsoft internal open-source
  release and repository-creation process;
- add issue and pull-request templates;
- document the supported Python and dependency policy;
- add CI for generators, validation, tests, secret scanning, and fixture checks;
- configure the Microsoft CLA status check and applicable repository policies.

## Remaining technical enhancements

- Automated unit and end-to-end tests.
- Privacy and reserved-name scanning.
- External configuration for telemetry fields and pricing.
- Deterministic Azure Workbook identifiers and generated-file consistency checks.
- Normalized evaluation result ingestion and run manifests.
