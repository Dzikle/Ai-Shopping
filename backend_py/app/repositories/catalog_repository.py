"""PostgreSQL catalog repository - 1:1 port of PostgresCatalogRepository.java.

SQL is unchanged (only JdbcTemplate `?` placeholders became psycopg `%s`).
All money/date shaping (scale-2, ISO instants) happens here so the HTTP layer
can compose camelCase DTO dicts directly, mirroring the Java records.
"""

from decimal import Decimal
from typing import Any

from app.services.unit_conversion import scale


def _s2(value) -> Decimal | None:
    """scale2 mirror (rs.getBigDecimal(...).setScale(2, HALF_UP))."""
    return scale(value, 2) if value is not None else None


class PostgresCatalogRepository:
    def __init__(self, db):
        self._db = db

    # ---- health ----

    def is_database_healthy(self) -> bool:
        try:
            return self._db.scalar("SELECT 1") == 1
        except Exception:
            return False

    def get_table_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in (
            "stores",
            "retailer_products",
            "offers_current",
            "price_observations",
            "canonical_products",
            "product_matches",
        ):
            counts[table] = self._count_table(table)
        return counts

    def _count_table(self, table: str) -> int:
        value = self._db.scalar(f"SELECT COUNT(*) FROM {table}")
        return int(value) if value is not None else 0

    # ---- stores (fallback) ----

    def find_stores(self, retailer: str | None, city: str | None):
        where = " WHERE 1=1 "
        params: list[Any] = []
        if retailer and retailer.strip():
            where += " AND LOWER(r.slug) = %s "
            params.append(retailer.strip().lower())
        if city and city.strip():
            where += " AND LOWER(s.city) = %s "
            params.append(city.strip().lower())

        sql = f"""
                SELECT s.id AS store_id,
                       r.slug AS retailer_slug,
                       r.name AS retailer_name,
                       s.external_key,
                       s.name,
                       s.address,
                       s.city,
                       COUNT(oc.retailer_product_id)::int AS active_offers_count,
                       MAX(oc.published_ts) AS latest_published_ts
                FROM stores s
                JOIN retailers r ON r.id = s.retailer_id
                LEFT JOIN offers_current oc ON oc.store_id = s.id
                {where}
                GROUP BY s.id, r.slug, r.name, s.external_key, s.name, s.address, s.city
                ORDER BY s.id ASC
                """

        items = []
        for row in self._db.query(sql, tuple(params)):
            items.append({
                "storeId": row["store_id"],
                "retailerSlug": row["retailer_slug"],
                "retailerName": row["retailer_name"],
                "externalKey": row["external_key"],
                "name": row["name"],
                "address": row["address"],
                "city": row["city"],
                "activeOffersCount": row["active_offers_count"],
                "latestPublishedTs": row["latest_published_ts"],
            })
        return {
            "sourceEngine": "postgresql_fallback",
            "total": len(items),
            "page": 0,
            "size": len(items),
            "items": items,
        }

    # ---- offers search (fallback) ----

    def search_offers(self, f):
        where = " WHERE 1=1 "
        params: list[Any] = []

        if f.q and f.q.strip():
            pattern = "%" + f.q.strip() + "%"
            where += " AND (rp.listing_name ILIKE %s OR COALESCE(cp.canonical_name, '') ILIKE %s OR COALESCE(rp.category, '') ILIKE %s) "
            params += [pattern, pattern, pattern]
        if f.retailer and f.retailer.strip():
            where += " AND LOWER(r.slug) = %s "
            params.append(f.retailer.strip().lower())
        if f.storeKey and f.storeKey.strip():
            where += " AND s.external_key = %s "
            params.append(f.storeKey.strip())
        if f.category and f.category.strip():
            where += " AND rp.category = %s "
            params.append(f.category.strip())
        if f.inStockOnly:
            where += " AND oc.availability = 'in_stock' "
        if f.promoOnly:
            where += " AND oc.promo_type IS NOT NULL AND oc.promo_type <> '' "
        if f.minPrice is not None:
            where += " AND oc.price_current >= %s "
            params.append(f.minPrice)
        if f.maxPrice is not None:
            where += " AND oc.price_current <= %s "
            params.append(f.maxPrice)

        joins = """
                FROM offers_current oc
                JOIN stores s ON s.id = oc.store_id
                JOIN retailers r ON r.id = s.retailer_id
                JOIN retailer_products rp ON rp.id = oc.retailer_product_id
                LEFT JOIN product_matches pm
                  ON pm.retailer_product_id = rp.id
                 AND pm.review_status IN ('auto_accepted', 'approved')
                LEFT JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                """

        total_value = self._db.scalar("SELECT COUNT(*) " + joins + where, tuple(params))
        total = int(total_value) if total_value is not None else 0

        sort_dir = "DESC" if (f.sort and (f.sort.lower() == "desc" or f.sort.lower() == "price_desc")) else "ASC"
        safe_size = max(1, f.size)
        safe_page = max(0, f.page)
        offset = safe_page * safe_size

        select_sql = f"""
                SELECT (oc.store_id::text || ':' || oc.retailer_product_id::text) AS offer_id,
                       oc.store_id,
                       s.external_key AS store_external_key,
                       s.name AS store_name,
                       s.city,
                       r.slug AS retailer_slug,
                       r.name AS retailer_name,
                       oc.retailer_product_id,
                       rp.sku_key,
                       rp.listing_name,
                       rp.category,
                       cp.id AS canonical_product_id,
                       cp.canonical_key,
                       cp.canonical_name,
                       cp.normalized_size,
                       trim(oc.currency) AS currency,
                       oc.price_current,
                       oc.unit_price,
                       oc.unit_label,
                       oc.regular_price,
                       oc.discount_price,
                       oc.discount_pct,
                       oc.promo_type,
                       oc.promo_starts_on,
                       oc.promo_ends_on,
                       (oc.promo_type IS NOT NULL AND oc.promo_type <> '') AS is_promo,
                       oc.availability,
                       oc.published_ts,
                       oc.fetched_ts,
                       oc.source_url,
                       oc.run_id
                {joins}{where} ORDER BY oc.price_current {sort_dir}, oc.store_id ASC, oc.retailer_product_id ASC LIMIT %s OFFSET %s
                """
        rows = self._db.query(select_sql, tuple(params) + (safe_size, offset))
        items = [self._map_offer_row(row) for row in rows]
        return {
            "sourceEngine": "postgresql_fallback",
            "total": total,
            "page": safe_page,
            "size": safe_size,
            "items": items,
        }

    @staticmethod
    def _map_offer_row(row) -> dict[str, Any]:
        return {
            "offerId": row["offer_id"],
            "storeId": row["store_id"],
            "storeExternalKey": row["store_external_key"],
            "storeName": row["store_name"],
            "city": row["city"],
            "retailerSlug": row["retailer_slug"],
            "retailerName": row["retailer_name"],
            "retailerProductId": row["retailer_product_id"],
            "skuKey": row["sku_key"],
            "listingName": row["listing_name"],
            "category": row["category"],
            "canonicalProductId": row["canonical_product_id"],
            "canonicalKey": row["canonical_key"],
            "canonicalName": row["canonical_name"],
            "normalizedSize": row["normalized_size"],
            "currency": row["currency"],
            "priceCurrent": _s2(row["price_current"]),
            "unitPrice": _s2(row["unit_price"]),
            "unitLabel": row["unit_label"],
            "regularPrice": _s2(row["regular_price"]),
            "discountPrice": _s2(row["discount_price"]),
            "discountPct": _s2(row["discount_pct"]),
            "promoType": row["promo_type"],
            "promoStartsOn": row["promo_starts_on"],
            "promoEndsOn": row["promo_ends_on"],
            "isPromo": bool(row["is_promo"]),
            "availability": row["availability"],
            "publishedTs": row["published_ts"],
            "fetchedTs": row["fetched_ts"],
            "sourceUrl": row["source_url"],
            "runId": row["run_id"],
        }

    # ---- product comparison (fallback) ----

    def compare_products(self, q: str | None, min_retailers: int, page: int, size: int):
        filter_clause = " WHERE retailer_count >= %s "
        params: list[Any] = [max(1, min_retailers)]

        if q and q.strip():
            pattern = "%" + q.strip() + "%"
            filter_clause += " AND (canonical_name ILIKE %s OR normalized_tokens ILIKE %s) "
            params += [pattern, pattern]

        cte = """
                WITH per_retailer AS (
                    SELECT cp.id AS canonical_product_id,
                           r.slug AS retailer_slug,
                           rp.id AS retailer_product_id,
                           rp.listing_name,
                           MIN(oc.price_current) AS min_price,
                           MAX(oc.price_current) AS max_price,
                           COUNT(DISTINCT oc.store_id)::int AS store_count,
                           MAX(oc.published_ts) AS latest_published_ts,
                           MIN(oc.source_url) AS source_url
                    FROM canonical_products cp
                    JOIN product_matches pm
                      ON pm.canonical_product_id = cp.id
                     AND pm.review_status IN ('auto_accepted', 'approved')
                    JOIN retailer_products rp ON rp.id = pm.retailer_product_id
                    JOIN retailers r ON r.id = rp.retailer_id
                    JOIN offers_current oc ON oc.retailer_product_id = rp.id
                    GROUP BY cp.id, r.slug, rp.id, rp.listing_name
                ),
                aggregated AS (
                    SELECT cp.id AS canonical_product_id,
                           cp.canonical_key,
                           cp.canonical_name,
                           cp.normalized_tokens,
                           cp.normalized_size,
                           COUNT(DISTINCT pr.retailer_slug)::int AS retailer_count,
                           COALESCE(SUM(pr.store_count), 0)::int AS store_count,
                           MIN(pr.min_price) AS min_price,
                           MAX(pr.max_price) AS max_price,
                           (MAX(pr.max_price) - MIN(pr.min_price)) AS spread_mkd,
                           MAX(pr.latest_published_ts) AS latest_published_ts,
                           COALESCE(
                               JSON_AGG(
                                   JSON_BUILD_OBJECT(
                                       'retailer_slug', pr.retailer_slug,
                                       'retailer_product_id', pr.retailer_product_id,
                                       'listing_name', pr.listing_name,
                                       'min_price', pr.min_price,
                                       'max_price', pr.max_price,
                                       'store_count', pr.store_count,
                                       'latest_published_ts', pr.latest_published_ts,
                                       'source_url', pr.source_url
                                   )
                                   ORDER BY pr.min_price, pr.retailer_slug
                               ) FILTER (WHERE pr.retailer_slug IS NOT NULL),
                               '[]'::json
                           )::text AS offers_json
                    FROM canonical_products cp
                    LEFT JOIN per_retailer pr ON pr.canonical_product_id = cp.id
                    GROUP BY cp.id, cp.canonical_key, cp.canonical_name, cp.normalized_tokens, cp.normalized_size
                )
                """

        total_value = self._db.scalar(cte + " SELECT COUNT(*) FROM aggregated " + filter_clause, tuple(params))
        total = int(total_value) if total_value is not None else 0

        safe_size = max(1, size)
        safe_page = max(0, page)
        offset = safe_page * safe_size

        select_sql = cte + f"""
                SELECT canonical_product_id,
                       canonical_key,
                       canonical_name,
                       normalized_size,
                       retailer_count,
                       store_count,
                       min_price,
                       max_price,
                       spread_mkd,
                       latest_published_ts,
                       offers_json
                FROM aggregated
                {filter_clause} ORDER BY canonical_name ASC LIMIT %s OFFSET %s
                """
        rows = self._db.query(select_sql, tuple(params) + (safe_size, offset))

        items = []
        for row in rows:
            items.append({
                "canonicalProductId": row["canonical_product_id"],
                "canonicalKey": row["canonical_key"],
                "canonicalName": row["canonical_name"],
                "normalizedSize": row["normalized_size"],
                "retailerCount": row["retailer_count"],
                "storeCount": row["store_count"],
                "cheapestMkd": _s2(row["min_price"]),
                "highestMkd": _s2(row["max_price"]),
                "spreadMkd": _s2(row["spread_mkd"]),
                "latestPublishedTs": row["latest_published_ts"],
                "offers": _parse_offers_json(row["offers_json"]),
            })
        return {
            "sourceEngine": "postgresql_fallback",
            "total": total,
            "page": safe_page,
            "size": safe_size,
            "items": items,
        }

    # ---- product history ----

    def get_product_history(self, canonical_product_id: int) -> dict[str, Any] | None:
        header = self._db.query_one(
            """
                SELECT id, canonical_name, normalized_size
                FROM canonical_products
                WHERE id = %s
                """,
            (canonical_product_id,),
        )
        if header is None:
            return None

        obs_sql = """
                SELECT po.id AS observation_id,
                       r.slug AS retailer_slug,
                       s.external_key AS store_external_key,
                       s.name AS store_name,
                       rp.listing_name,
                       po.price_current,
                       po.regular_price,
                       po.discount_price,
                       po.discount_pct,
                       po.promo_type,
                       po.availability,
                       po.published_ts,
                       po.fetched_ts,
                       po.source_url
                FROM product_matches pm
                JOIN retailer_products rp ON rp.id = pm.retailer_product_id
                JOIN retailers r ON r.id = rp.retailer_id
                JOIN price_observations po ON po.retailer_product_id = rp.id
                JOIN stores s ON s.id = po.store_id
                WHERE pm.canonical_product_id = %s
                  AND pm.review_status IN ('auto_accepted', 'approved')
                ORDER BY po.published_ts DESC NULLS LAST, r.slug ASC, s.external_key ASC
                """
        observations = []
        for row in self._db.query(obs_sql, (canonical_product_id,)):
            observations.append({
                "observationId": row["observation_id"],
                "retailerSlug": row["retailer_slug"],
                "storeExternalKey": row["store_external_key"],
                "storeName": row["store_name"],
                "listingName": row["listing_name"],
                "priceCurrent": _s2(row["price_current"]),
                "regularPrice": _s2(row["regular_price"]),
                "discountPrice": _s2(row["discount_price"]),
                "discountPct": _s2(row["discount_pct"]),
                "promoType": row["promo_type"],
                "availability": row["availability"],
                "publishedTs": row["published_ts"],
                "fetchedTs": row["fetched_ts"],
                "sourceUrl": row["source_url"],
            })

        return {
            "canonicalProductId": header["id"],
            "canonicalName": header["canonical_name"],
            "normalizedSize": header["normalized_size"],
            "observations": observations,
        }

    # ---- review queue ----

    def get_review_queue(self, limit: int) -> list[dict[str, Any]]:
        safe_limit = max(1, min(200, limit))
        sql = """
                SELECT pm.id AS match_id,
                       r.slug AS source_retailer_slug,
                       rp.id AS retailer_product_id,
                       rp.listing_name AS source_listing_name,
                       cp.id AS candidate_canonical_id,
                       cp.canonical_name AS candidate_canonical_name,
                       cp.normalized_size,
                       pm.confidence,
                       pm.review_status,
                       pm.evidence::text AS evidence_json
                FROM product_matches pm
                JOIN retailer_products rp ON rp.id = pm.retailer_product_id
                JOIN retailers r ON r.id = rp.retailer_id
                JOIN canonical_products cp ON cp.id = pm.canonical_product_id
                WHERE pm.review_status = 'pending_review'
                ORDER BY pm.confidence DESC, rp.listing_name ASC
                LIMIT %s
                """
        items = []
        for row in self._db.query(sql, (safe_limit,)):
            items.append({
                "matchId": row["match_id"],
                "sourceRetailerSlug": row["source_retailer_slug"],
                "retailerProductId": row["retailer_product_id"],
                "sourceListingName": row["source_listing_name"],
                "candidateCanonicalId": row["candidate_canonical_id"],
                "candidateCanonicalName": row["candidate_canonical_name"],
                "normalizedSize": row["normalized_size"],
                "confidence": _s2(row["confidence"]),
                "reviewStatus": row["review_status"],
                "evidence": _parse_evidence(row["evidence_json"]),
            })
        return items

    def approve_match(self, match_id: int, reviewed_by: str | None, review_notes: str | None) -> dict[str, Any]:
        return self._review_decision(
            match_id, "approve", "approved", reviewed_by, review_notes
        )

    def reject_match(self, match_id: int, reviewed_by: str | None, review_notes: str | None) -> dict[str, Any]:
        return self._review_decision(
            match_id, "reject", "rejected", reviewed_by, review_notes
        )

    def _review_decision(
        self, match_id: int, action: str, new_status: str,
        reviewed_by: str | None, review_notes: str | None,
    ) -> dict[str, Any]:
        rowcount = self._db.execute(
            f"""
                UPDATE product_matches
                SET review_status = '{new_status}',
                    reviewed_by = %s,
                    reviewed_at = now(),
                    review_notes = %s,
                    updated_at = now()
                WHERE id = %s AND review_status = 'pending_review'
                """,
            (reviewed_by, review_notes, match_id),
        )
        if not rowcount:
            raise ValueError(
                f"match id {match_id} not found or not in pending_review status"
            )
        return {
            "matchId": match_id,
            "reviewStatus": new_status,
            "reviewedBy": reviewed_by,
            "reviewNotes": review_notes,
        }

    # ---- metrics ----

    def get_metrics(self) -> dict[str, Any]:
        checked_at = self._db.scalar("SELECT now()")

        total_offers = int(self._db.scalar("SELECT COUNT(*) FROM offers_current") or 0)
        total_observations = int(self._db.scalar("SELECT COUNT(*) FROM price_observations") or 0)
        total_canonical = int(self._db.scalar("SELECT COUNT(*) FROM canonical_products") or 0)
        total_matches = int(self._db.scalar("SELECT COUNT(*) FROM product_matches") or 0)

        populated_stores = int(self._db.scalar(
            "SELECT COUNT(DISTINCT store_id) FROM offers_current") or 0)

        stale_stores = int(self._db.scalar(
            "SELECT COUNT(*) FROM (SELECT s.id FROM stores s JOIN offers_current oc ON oc.store_id = s.id "
            "GROUP BY s.id HAVING MAX(oc.published_ts) < now() - INTERVAL '48 hours') sub") or 0)

        quarantined_runs = int(self._db.scalar(
            "SELECT COUNT(*) FROM ingestion_runs WHERE quarantined = true AND started_at >= now() - INTERVAL '7 days'") or 0)

        runs_sql = """
                SELECT id, run_key, source_slug, status, started_at, finished_at,
                       pages_seen, rows_seen, rows_stored, rows_skipped, quarantined,
                       quarantine_reason, worker_id,
                       EXTRACT(EPOCH FROM (COALESCE(finished_at, now()) - started_at))::double precision AS duration_seconds
                FROM ingestion_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 20
                """
        recent_runs = []
        for row in self._db.query(runs_sql):
            recent_runs.append({
                "runId": row["id"],
                "runKey": row["run_key"],
                "sourceSlug": row["source_slug"],
                "status": row["status"],
                "startedAt": row["started_at"],
                "finishedAt": row["finished_at"],
                "pagesSeen": row["pages_seen"],
                "rowsSeen": row["rows_seen"],
                "rowsStored": row["rows_stored"],
                "rowsSkipped": row["rows_skipped"],
                "quarantined": bool(row["quarantined"]),
                "quarantineReason": row["quarantine_reason"],
                "workerId": row["worker_id"],
                "durationSeconds": row["duration_seconds"],
            })

        pending = int(self._db.scalar(
            "SELECT COUNT(*) FROM product_matches WHERE review_status = 'pending_review'") or 0)
        approved = int(self._db.scalar(
            "SELECT COUNT(*) FROM product_matches WHERE review_status = 'approved'") or 0)
        rejected = int(self._db.scalar(
            "SELECT COUNT(*) FROM product_matches WHERE review_status = 'rejected'") or 0)
        auto_accepted = int(self._db.scalar(
            "SELECT COUNT(*) FROM product_matches WHERE review_status = 'auto_accepted'") or 0)
        oldest_pending_days = int(self._db.scalar(
            "SELECT COALESCE(EXTRACT(DAY FROM (now() - MIN(created_at)))::int, 0) FROM product_matches WHERE review_status = 'pending_review'") or 0)

        return {
            "checkedAt": checked_at,
            "totalOffers": total_offers,
            "totalObservations": total_observations,
            "totalCanonicalProducts": total_canonical,
            "totalProductMatches": total_matches,
            "totalPendingReview": pending,
            "totalPopulatedStores": populated_stores,
            "totalStaleStores": stale_stores,
            "totalQuarantinedRuns": quarantined_runs,
            "recentRuns": recent_runs,
            "reviewQueue": {
                "totalPending": pending,
                "totalApproved": approved,
                "totalRejected": rejected,
                "totalAutoAccepted": auto_accepted,
                "oldestPendingDays": oldest_pending_days,
            },
        }

    # ---- freshness ----

    def get_freshness(self, retailer: str | None, stale_threshold_hours: int, quarantine_window_days: int) -> dict[str, Any]:
        safe_stale_hours = max(1, min(87600, stale_threshold_hours))
        safe_quarantine_days = max(1, min(365, quarantine_window_days))

        checked_at = self._db.scalar("SELECT now()")

        retailer_where = " WHERE 1=1 "
        retailer_params: list[Any] = []
        if retailer and retailer.strip():
            retailer_where += " AND LOWER(r.slug) = %s "
            retailer_params.append(retailer.strip().lower())

        # 1. Quarantined runs within quarantineWindowDays
        q_where = (
            " WHERE (ir.quarantined = true OR ir.status = 'quarantined') "
            "   AND ir.started_at >= (now() - (%s * INTERVAL '1 day')) "
        )
        q_params: list[Any] = [safe_quarantine_days]
        if retailer and retailer.strip():
            q_where += " AND LOWER(ir.source_slug) = %s "
            q_params.append(retailer.strip().lower())
        q_sql = f"""
                SELECT ir.id AS run_id,
                       ir.run_key,
                       ir.source_slug,
                       ir.status,
                       ir.started_at,
                       ir.finished_at,
                       ir.pages_seen,
                       ir.rows_seen,
                       ir.quarantine_reason,
                       ir.worker_id
                FROM ingestion_runs ir
                {q_where} ORDER BY ir.started_at DESC, ir.id DESC
                """
        quarantined_runs = []
        for row in self._db.query(q_sql, tuple(q_params)):
            quarantined_runs.append({
                "runId": row["run_id"],
                "runKey": row["run_key"],
                "sourceSlug": row["source_slug"],
                "status": row["status"],
                "startedAt": row["started_at"],
                "finishedAt": row["finished_at"],
                "pagesSeen": row["pages_seen"],
                "rowsSeen": row["rows_seen"],
                "quarantineReason": row["quarantine_reason"],
                "workerId": row["worker_id"],
            })

        quarantined_by_retailer: dict[str, int] = {}
        for qr in quarantined_runs:
            slug = (qr["sourceSlug"] or "").lower() if qr["sourceSlug"] else ""
            quarantined_by_retailer[slug] = quarantined_by_retailer.get(slug, 0) + 1

        # 2. Populated store freshness and stale stores detection
        store_sql = f"""
                SELECT r.slug AS retailer_slug,
                       s.id AS store_id,
                       s.external_key,
                       s.name AS store_name,
                       s.city,
                       COUNT(oc.retailer_product_id)::int AS offer_count,
                       MAX(oc.published_ts) AS latest_published_ts,
                       MAX(oc.fetched_ts) AS latest_fetched_ts,
                       ROUND(EXTRACT(EPOCH FROM (now() - MAX(oc.published_ts))) / 3600.0, 2) AS age_hours
                FROM stores s
                JOIN retailers r ON r.id = s.retailer_id
                JOIN offers_current oc ON oc.store_id = s.id
                {retailer_where}
                GROUP BY r.slug, s.id, s.external_key, s.name, s.city
                HAVING MAX(oc.published_ts) < (now() - (%s * INTERVAL '1 hour'))
                ORDER BY r.slug ASC, s.id ASC
                """
        store_params = tuple(retailer_params) + (safe_stale_hours,)

        stale_stores_by_retailer: dict[str, list[dict[str, Any]]] = {}
        for row in self._db.query(store_sql, store_params):
            slug = row["retailer_slug"].lower()
            dt_item = {
                "storeId": row["store_id"],
                "externalKey": row["external_key"],
                "storeName": row["store_name"],
                "city": row["city"],
                "offerCount": row["offer_count"],
                "latestPublishedTs": row["latest_published_ts"],
                "latestFetchedTs": row["latest_fetched_ts"],
                "ageHours": _s2(row["age_hours"]),
            }
            stale_stores_by_retailer.setdefault(slug, []).append(dt_item)

        # 3. Per-retailer aggregates + latest completed ingestion run
        retailer_sql = f"""
                SELECT r.slug AS retailer_slug,
                       r.name AS retailer_name,
                       COUNT(DISTINCT s.id)::int AS seeded_stores_count,
                       COUNT(DISTINCT oc.store_id)::int AS populated_stores_count,
                       COUNT(oc.retailer_product_id)::bigint AS offer_count,
                       MAX(oc.published_ts) AS latest_published_ts,
                       MIN(oc.published_ts) AS oldest_published_ts,
                       MAX(oc.fetched_ts) AS latest_fetched_ts,
                       (SELECT ir.run_key
                        FROM ingestion_runs ir
                        WHERE LOWER(ir.source_slug) = LOWER(r.slug)
                          AND ir.status = 'completed'
                        ORDER BY ir.finished_at DESC NULLS LAST, ir.id DESC
                        LIMIT 1) AS last_completed_run_key,
                       (SELECT ir.finished_at
                        FROM ingestion_runs ir
                        WHERE LOWER(ir.source_slug) = LOWER(r.slug)
                          AND ir.status = 'completed'
                        ORDER BY ir.finished_at DESC NULLS LAST, ir.id DESC
                        LIMIT 1) AS last_completed_at
                FROM retailers r
                LEFT JOIN stores s ON s.retailer_id = r.id
                LEFT JOIN offers_current oc ON oc.store_id = s.id
                {retailer_where}
                GROUP BY r.id, r.slug, r.name
                ORDER BY r.slug ASC
                """
        retailers = []
        for row in self._db.query(retailer_sql, tuple(retailer_params)):
            slug = row["retailer_slug"]
            key = slug.lower() if slug else ""
            stale_list = stale_stores_by_retailer.get(key, [])
            q_count = quarantined_by_retailer.get(key, 0)
            retailers.append({
                "retailerSlug": slug,
                "retailerName": row["retailer_name"],
                "seededStoresCount": row["seeded_stores_count"],
                "populatedStoresCount": row["populated_stores_count"],
                "offerCount": row["offer_count"],
                "latestPublishedTs": row["latest_published_ts"],
                "oldestPublishedTs": row["oldest_published_ts"],
                "latestFetchedTs": row["latest_fetched_ts"],
                "staleStoresCount": len(stale_list),
                "staleStores": stale_list,
                "quarantinedRunsCount": q_count,
                "lastCompletedRunKey": row["last_completed_run_key"],
                "lastCompletedAt": row["last_completed_at"],
            })

        total_offers = sum(r["offerCount"] for r in retailers)
        total_populated_stores = sum(r["populatedStoresCount"] for r in retailers)
        total_stale_stores = sum(r["staleStoresCount"] for r in retailers)
        total_quarantined_runs = len(quarantined_runs)

        if total_offers == 0:
            status = "EMPTY"
        elif total_stale_stores > 0 or total_quarantined_runs > 0:
            status = "DEGRADED"
        else:
            status = "FRESH"

        return {
            "status": status,
            "checkedAt": checked_at,
            "staleThresholdHours": safe_stale_hours,
            "quarantineWindowDays": safe_quarantine_days,
            "totalOffers": total_offers,
            "totalPopulatedStores": total_populated_stores,
            "totalStaleStores": total_stale_stores,
            "totalQuarantinedRuns": total_quarantined_runs,
            "retailers": retailers,
            "quarantinedRuns": quarantined_runs,
        }


def _parse_offers_json(raw: str | None) -> list[dict[str, Any]]:
    import json

    if raw is None or not raw.strip():
        return []
    try:
        arr = json.loads(raw)
        result = []
        for o in arr:
            ts = None
            value = o.get("latest_published_ts")
            if value is not None and str(value).strip():
                ts = _instantiate(str(value))
            result.append({
                "retailerSlug": o.get("retailer_slug"),
                "retailerProductId": o.get("retailer_product_id"),
                "listingName": o.get("listing_name"),
                "minPrice": _s2(o.get("min_price")) if o.get("min_price") is not None else None,
                "maxPrice": _s2(o.get("max_price")) if o.get("max_price") is not None else None,
                "storeCount": o.get("store_count") or 0,
                "latestPublishedTs": ts,
                "sourceUrl": o.get("source_url"),
            })
        return result
    except Exception:
        return []


def _instantiate(raw: str):
    import datetime as dt

    return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def _parse_evidence(raw: str | None) -> dict[str, Any]:
    import json

    if raw is None or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}
