# AI Shopping — Universal Price Intelligence Platform

A retailer-agnostic platform for daily price ingestion, canonical product matching, store-level comparison, price history, and AI-assisted grocery shopping. **Status: planning / M0.** No deployed implementation is implied.

Initial focus: North Macedonia. Expansion: other countries, retailers and product categories.

Start with [the master plan](docs/architecture/master-plan.md), [the milestone roadmap](docs/milestones/roadmap.md) and [AGENTS.md](AGENTS.md).

Core design: Spring Boot / Java 21, PostgreSQL source of truth, OpenSearch derived indexes, independent Python/TypeScript adapters, optional Redis worker queues, Docker Compose, MCP read-only tools. Exact versions and compatibility must be verified during M0.
