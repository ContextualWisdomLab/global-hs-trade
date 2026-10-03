# Repository working agreement

The scope is global company-by-HS **observations**, not a fabricated all-company census. Start by reading the current branch, open PRs, reviews, checks and organization rules. Work in a dedicated branch; do not overwrite another writer's files or bypass reviews. Do not modify sibling repositories as part of work here.

Preserve the domain boundaries: `trade` owns observation validation and aggregation; `identity` owns source-scoped or supplied registry identities; `sources` owns upstream parsing; `collection` owns evidence and resumable collection; `coverage` owns availability and actual inventory. Storage and transport must not decide trade meaning.

Keep company domicile separate from reporting territory, party roles distinct, national totals separate from company observations, HS revision/evidence origin explicit, and missing values as null. Do not combine currencies, valuation bases, provenance or incompatible HS editions. A hash is not authenticity proof. Synthetic inputs must stay visibly synthetic.

Use regression-first fixes. Run `python scripts/check.py` and `python scripts/verify_install.py` before claiming completion. Verify checks at the exact pushed SHA. Resolve warnings/deprecations at their cause; unresolved findings require a concrete issue with evidence and an acceptance test, not a permanent blanket exception.

Do not hold database transactions or explicit locks across network, LLM, parsing or expensive calculation. Prepare outside transactions and keep writes short. No `.env` or plaintext credentials. Future secret-bearing adapters must consume a versioned Keyverse contract; no Keyverse integration is claimed in this baseline.

Use Python snake_case for functions, variables and modules, PascalCase for classes, and descriptive identifiers for persisted fields. Preserve established externally visible schemas unless a versioned migration is provided. Comments should explain constraints and decisions, not restate code.

This is a public repository. Do not commit actual trade captures, vendor exports, private company records, credentials, SQLite files or build artifacts. Source access and redistribution are separate permissions. Use synthetic fixtures to reproduce edge cases.
