# Python and Dependency Support Policy

## Supported Python versions

The project supports the latest patch releases of CPython 3.11, 3.12, 3.13, and
3.14.

- Python 3.11 is the minimum supported version.
- PyPy and other Python implementations are not currently supported.
- A newly released CPython feature version becomes supported after the project
  passes its validation workflow on that version.
- A Python feature version may be removed after it reaches upstream end of life.
  The removal must be documented as a compatibility change.

Contributors must not introduce syntax or standard-library features newer than
Python 3.11 unless the minimum supported version is intentionally raised.

## Runtime dependency model

The core evaluation workflow uses only the Python standard library. This includes:

- Application Insights CSV conversion;
- canonical JSONL validation;
- Copilot Studio and Copilot Studio Kit CSV generation;
- baseline-template generation and summarization;
- latency-dataset generation;
- API and KQL command-line helpers;
- Azure Workbook generation.

The following packages are optional and are listed in
[`requirements-optional.txt`](../requirements-optional.txt):

| Package | Supported range | Used by |
| --- | --- | --- |
| `Pillow` | `>=10,<13` | `scripts/generate_banking_flow_image.py` |
| `python-pptx` | `>=1,<2` | `scripts/generate_report_templates.py` |

Install these packages only when regenerating the corresponding image or
PowerPoint artifacts:

```powershell
python -m pip install -r requirements-optional.txt
```

External tools such as Azure CLI and GitHub CLI are workflow integrations, not
Python package dependencies. Their use is optional and documented by the commands
that require them.

## Version constraints and reproducibility

`requirements-optional.txt` defines compatible direct-dependency ranges; it is not
a lock file. This repository is a collection of scripts and examples rather than
an installable Python package, so it does not currently publish a `pyproject.toml`
or a resolved dependency lock.

For a recorded evaluation or report-generation run:

1. Record the Python version.
2. Record installed optional package versions when those packages are used.
3. Preserve the canonical input and generated output with the run metadata.

Consumers that require bit-for-bit environment reproducibility should create and
retain a lock file in their deployment or automation environment.

## Adding and updating dependencies

- Prefer the standard library when it provides a clear and maintainable solution.
- Add a third-party dependency only when its benefit outweighs its maintenance,
  security, licensing, and supply-chain cost.
- Use maintained packages with licenses compatible with the MIT License.
- Declare direct dependencies with a tested lower bound and a protective upper
  bound for the next incompatible major version.
- Do not add an unused, transitive, or convenience-only package to the requirements
  file.
- Test major-version upgrades before widening an upper bound.
- Review dependency updates regularly and enable Dependabot when repository
  automation is configured.
- Prioritize security updates. Report suspected vulnerabilities according to
  [`SECURITY.md`](../SECURITY.md), not through a public issue.

## Platform policy

The scripts are designed to run on Windows, Linux, and macOS. Documentation uses
PowerShell examples because the reference project was prepared on Windows.
Platform-specific behavior must use standard-library abstractions such as
`pathlib` rather than hard-coded path separators.

The planned CI matrix should exercise each supported Python version and the
operating systems needed by active maintainers. Until that automation is present,
contributors must report the Python version and operating system used for manual
validation.
