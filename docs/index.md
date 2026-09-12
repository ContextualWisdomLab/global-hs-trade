# Global HS Trade

Global HS Trade is an evidence-aware ledger and local API for collecting, validating, and aggregating rights-scoped company-by-HS trade observations.

## Current status

The repository contains a proposed v0.2.0 import. It does not include a global company census, commercial customs-data rights, production IAM, a hosted multi-tenant service, or a release. Open pull requests and documentation remain candidate evidence until they reach the protected default branch.

## Start here

- [Repository overview](../README.md)
- [Design and bounded contexts](DESIGN.md)
- [Data contract](DATA_CONTRACT.md)
- [Evidence capture contract](CAPTURE_CONTRACT.md)
- [Source acquisition boundary](SOURCE_ACQUISITION.md)
- [Known limitations](LIMITATIONS.md)
- [Repository import evidence](REPOSITORY_IMPORT.md)
- [Ask DeepWiki](https://deepwiki.com/ContextualWisdomLab/global-hs-trade)

## Product boundary

Global HS Trade owns source-scoped trade observations, evidence-aware ingestion, role-preserving aggregation, coverage reporting, and a local read-only query interface. It keeps company domicile separate from reporting territory, national totals separate from company observations, and missing values distinct from zero.

## Data and publication boundary

The public repository uses synthetic fixtures and does not publish private company records, vendor exports, real trade captures, credentials, or redistribution rights. This file is a documentation landing source. GitHub Pages availability is separate repository state and must be verified live before it is presented as published.
