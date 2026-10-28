# Agent instructions

## Scope
Execute **M0 only** until the owner approves M1. This repository is `Dzikle/Ai-Shopping`; do not create a replacement repository. Local development clone should be `C:\Dev\Personal\ao shopping`, outside OneDrive.

1. Inspect before editing. Audit the four upstream repositories, pin commit hashes and record code-level reuse suitability and licenses.
2. Keep architecture modular and contracts explicit. No unapproved paid APIs, cloud resources, deployment or destructive actions.
3. Preserve data provenance, source timestamps, unit/pack sizes and location-specific prices.
4. PostgreSQL is authoritative; OpenSearch is a rebuildable projection.
5. Product identity is distinct from product equivalence/substitution.
6. Treat empty/abnormal scraped catalogs as failed or quarantined runs, not as a reason to delete live offers.
7. Respect retailer terms, robots directives where applicable, rate limits, access controls and legal restrictions.
8. Every milestone: committed changes, reproducible tests, documentation, execution evidence, limitations and owner approval.
9. Never claim work done without verified output. Keep `docs/milestones/current-status.md` updated.
10. Agent may propose architecture improvements but must not silently implement post-M0 milestones.

## First work package
- Verify repository configuration and versions of proposed dependencies.
- Complete `docs/research/open-source-reuse-audit.md` with exact source files/commits.
- Validate primary retailer price-list endpoints and legal/terms constraints.
- Produce ADRs, minimal runnable baseline + CI, and a concrete M1 proposal.
- Stop for owner review.
