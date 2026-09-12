# 0.2.0 repository integration

The user designated `ContextualWisdomLab/global-hs-trade` as the development repository. Its initial `main` commit was `1f7c891c3b86f3e4050d7c14c34d6208f83b6aa7`, with only `LICENSE`. The existing license blob `b3160d62e0d16afc0cea1a0174a2da19e5d3bdd3` is preserved byte-for-byte.

## Input and migration

Input: `global-hs-trade-v0.2.0.zip`, SHA-256 `f0a9fa183b2eef515480bd20c28a7acd6493b0d950981399b0bd553f8885aa3b`. All 117 manifest entries were checked before migration. The original suite passed 156 tests in this session.

Runtime source modules are imported from the archive. Development metadata adds the existing MIT license to the wheel. The runtime version remains 0.2.0: this integration is not a new release.

Original third-party factual captures, real-company observations, national aggregate samples, SQLite databases, wheels, generated manifests and historical execution logs are excluded from the public repository. Their presence in a conversation attachment did not establish a public redistribution grant.

The 0.2.0 sample assertions are retained as independently generated synthetic regression cases: role misattribution, unknown buyer domicile, quantity versus net weight, presence versus shipments/money, exact Decimal values, provenance and replay remain tested. No factual-company names or captured vendor data are required by the public test suite.

## Repository-specific work

- Added a deterministic synthetic-only demo builder. It stages a new DB on the same filesystem and publishes with an exclusive hard link; existing files and symlinks cannot be overwritten. Invalid or rejected imports do not publish partial DBs.
- Added installation verification that builds a wheel, preserves LICENSE and the country data file, installs in a fresh virtual environment without an index, and checks a synthetic query outside the source directory.
- Added SHA-pinned product CI for Python 3.11, 3.12 and 3.13 with read-only repository permissions and no secrets. Organization review/security workflows are not modified.
- Added working agreements, setup instructions, ignore rules for data/secrets/build output, and explicit source-rights boundaries.

## Verification boundary

The compact local receipt is in `evidence/repository-import.json`. Local tests ran on Python 3.13.5. CI on other versions is configured but must be evaluated at the published commit. Direct external HTTP was blocked by DNS in the local execution environment; no live upstream freshness or complete geographic coverage is claimed. No release, deployment, paid feed purchase or credentials change was performed.
