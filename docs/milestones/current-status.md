# Project status — 2026-10-28

## Implemented (M0, this session)
- **Dependency verification:** Spring Boot 4.1.2 GA (stable), OpenSearch 3.9.0 (2026-09-29), PostgreSQL 18.6 (current 18.x), Java 21 LTS — all compatible with the planned stack. Recorded in ADR-0001/0002.
- **Upstream reuse audit completed:** all four candidate repos audited at pinned commits (`2f951f1` KortingKlok/archived, `aff6880` open-supermarkets, `efb2e0a` checkjebon, `36d5992` price-scraper), MIT confirmed via license blob SHAs, exact reusable file paths recorded in `docs/research/open-source-reuse-audit.md`.
- **Retailer validation:** Vero pricelist fully validated (static HTML, per-store paginated pages `{storeId}_{page}.html`, unit prices, promotions, last-updated timestamp) → recommended first source; Ramstore blocked by its own site terms pending written consent; KAM format unresolved. See `docs/research/retailer-sources.md` and ADR-0005.
- **ADRs 0001–0005** written in `docs/adr/`.
- **Baseline + CI:** `docker-compose.yml` (PostgreSQL + OpenSearch, image-pinned, healthchecked; images overridable via env for local runs), `scripts/validate-baseline.ps1` (also validates .env parsing and versions), `.github/workflows/ci.yml` (docs check + full stack up --wait + validation + teardown), `.gitattributes` (LF normalization).

## Execution evidence (2026-10-28, local)
- `scripts/validate-baseline.ps1 -SkipOpenSearch` → container healthy, `SHOW server_version;` → **18.3**, output `BASELINE OK`.
- `docker compose config` validates both services (postgres, opensearch); `docker compose down` clean teardown.
- Full-stack run including OpenSearch **pending locally**: no OpenSearch image is cached and Docker Desktop's credential helper rejects pulls from non-interactive (session 0) shells by design. CI (GitHub Actions ubuntu) runs the full stack including OpenSearch 3.9.0 — verify on first push.
- Local Postgres runs 18.3 (cached image) via `POSTGRES_IMAGE=postgres:18.3` override; CI pins 18.6. Same major version; acceptable for M0.

## Blockers / limitations
- Java, Maven, Python, psql not installed natively on this machine (containers and CI provide them; `maven:3.9.9-eclipse-temurin-21` already cached).
- Docker image pulls fail from agent/automation shells (credential helper requires an interactive session). Workaround used: locally cached images; new images must be pulled by the owner or via CI.
- Local clone lives at `C:\Dev\Personal\ao shopping` (outside OneDrive ✓).

## Pending owner decisions (from `docs/milestones/m1-proposal.md`)
1. Approve M1 scope.
2. Daily fetch window after 08:30 local — acceptable?
3. Committing real captured Vero HTML fixtures to the repo — acceptable?
4. Owner action: request written consent from Ramstore Macedonia DOO if Ramstore ingestion is ever wanted.

## Next smallest testable task (after approval)
M1: Flyway schema + Vero parser with real fixtures + idempotency test.
