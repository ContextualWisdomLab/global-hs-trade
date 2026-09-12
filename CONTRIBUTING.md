# Contributing

Read `AGENTS.md` and the contracts under `docs/` before changing ingestion or aggregation. Keep changes in a feature branch and submit a pull request. Organization-required reviews and workflows still apply; the product CI does not replace them.

Use a Python 3.11+ virtual environment and install the reviewed development artifacts with `python -m pip install --require-hashes --no-deps -r requirements-dev.txt`. Add a failing regression for a behavior change, implement the smallest causal fix, then run:

```bash
python scripts/check.py
python -W error -m compileall -q global_hs_trade scripts
python scripts/verify_install.py
```

Do not include real customer/vendor data in a bug report. Reproduce with clearly synthetic inputs and preserve the relevant roles, valuation basis, missingness and source-version behavior. Report network failures as failures, not as successful empty datasets.

No release or production deployment is performed by this repository's CI. Publish artifacts only after review, exact-head verification and a separate authorized release decision.
