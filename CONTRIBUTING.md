# Contributing

This project welcomes contributions and suggestions.

## Contributor License Agreement

Most contributions require you to agree to a Contributor License Agreement (CLA)
declaring that you have the right to, and actually do, grant us the rights to use
your contribution. For details, visit
[Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you
need to provide a CLA and decorate the pull request appropriately, for example with
a status check or comment. Follow the instructions provided by the bot. You only
need to complete this process once across repositories that use the Microsoft CLA.

## Before contributing

1. Search existing issues before opening a duplicate.
2. Open an issue before making a substantial behavioral, schema, or architecture
   change so the approach can be discussed.
3. Read [AGENTS.md](AGENTS.md), [process.md](process.md), and
   [architecture.md](architecture.md).
4. Do not include production conversations, personal data, credentials, tenant or
   environment identifiers, internal URLs, or confidential agent configuration.

## Development

The core scripts require Python 3.11 or later and use the standard library. Install
optional dependencies only when working on image, PowerPoint, or API helpers:

```powershell
python -m pip install -r requirements-optional.txt
```

Review the [Python and dependency support policy](docs/python-support-policy.md)
before changing runtime requirements or adding a dependency.

Keep changes agent-agnostic unless they update the explicitly synthetic banking
example. Put agent-specific mappings in configuration or adapters rather than in
generic converters.

Before submitting a pull request:

1. Validate changed evaluation files:

   ```powershell
   python scripts\validate_eval_jsonl.py <evaluation.jsonl>
   ```

2. Regenerate any derived CSV, image, report, or Workbook files affected by the
   change.
3. Confirm generated artifacts contain no secrets, personal data, internal
   identifiers, or unintended production content.
4. Update documentation when commands, schemas, configuration, or behavior change.
5. Keep the pull request focused and describe its validation and generated-file
   impact.

All submissions, including submissions by project members, require review through
GitHub pull requests.

## Code of Conduct

This project has adopted the
[Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information, see the
[Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with questions or
concerns.

## Reporting security issues

Do not report security vulnerabilities through public issues. Follow the
instructions in [SECURITY.md](SECURITY.md).
