# ADR-0004: Immutable raw snapshots; quarantine instead of deletion

- **Status:** Accepted (2026-10-28)
- **Context:** Sources change silently; disputes and audits require reproducing what was captured. Unexpectedly empty or abnormal catalogs usually indicate a broken source or parser, not a mass product recall.
- **Decision:** Every fetch is stored verbatim (content hash, source URL, fetch timestamp, retailer-published timestamp when present) in a filesystem archive initially; an S3-compatible object store may replace it when justified. Parsed rows always reference the snapshot they came from (`run_id`). If a run yields unexpectedly empty or anomalous catalogs, the run is marked failed/quarantined and prior live offers are **kept**; nothing is deleted automatically.
- **Consequences:** Storage grows monotonically (acceptable at MK scale); dedup by content hash; retention policy deferred to M6.
