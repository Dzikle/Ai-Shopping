-- V1__m1_schema.sql — M1 schema: Vero single-source ingestion.
-- Flyway-compatible naming; applied by scripts/apply-migrations.ps1 until Spring Boot adopts Flyway.

SET client_encoding = 'UTF8';

BEGIN;

CREATE TABLE retailers (
    id           SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    country_code CHAR(2) NOT NULL DEFAULT 'MK',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE stores (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer_id  SMALLINT NOT NULL REFERENCES retailers(id),
    external_key TEXT NOT NULL,
    name         TEXT NOT NULL,
    address      TEXT,
    city         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (retailer_id, external_key)
);

-- M1 limitation: sku_key is derived from normalized listing name + category
-- (sources publish no GTIN). Real identity resolution arrives in M2 (ADR-0003).
CREATE TABLE retailer_products (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer_id  SMALLINT NOT NULL REFERENCES retailers(id),
    sku_key      TEXT NOT NULL,
    listing_name TEXT NOT NULL,
    category     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (retailer_id, sku_key)
);

CREATE TABLE ingestion_runs (
    id                INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_key           TEXT NOT NULL UNIQUE,
    source_slug       TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running', 'completed', 'quarantined', 'failed')),
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    pages_seen        INT,
    rows_seen         INT,
    rows_stored       INT,
    rows_skipped      INT,
    quarantined       BOOLEAN NOT NULL DEFAULT false,
    quarantine_reason TEXT,
    notes             TEXT
);

CREATE TABLE raw_snapshots (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        INT NOT NULL REFERENCES ingestion_runs(id),
    source_slug   TEXT NOT NULL,
    url           TEXT NOT NULL,
    url_hash      CHAR(64) NOT NULL,
    content_hash  CHAR(64) NOT NULL,
    storage_path  TEXT NOT NULL,
    content_type  TEXT,
    byte_size     BIGINT NOT NULL,
    fetched_ts    TIMESTAMPTZ NOT NULL,
    published_ts  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_slug, url_hash, content_hash)
);

CREATE TABLE offers_current (
    store_id            INT NOT NULL REFERENCES stores(id),
    retailer_product_id INT NOT NULL REFERENCES retailer_products(id),
    currency            CHAR(3) NOT NULL DEFAULT 'MKD',
    price_current       NUMERIC(12,2) NOT NULL CHECK (price_current >= 0),
    unit_price          NUMERIC(12,2) CHECK (unit_price IS NULL OR unit_price >= 0),
    unit_label          TEXT,
    regular_price       NUMERIC(12,2) CHECK (regular_price IS NULL OR regular_price >= 0),
    discount_price      NUMERIC(12,2) CHECK (discount_price IS NULL OR discount_price >= 0),
    discount_pct        NUMERIC(5,2)  CHECK (discount_pct IS NULL OR (discount_pct >= 0 AND discount_pct <= 100)),
    promo_type          TEXT,
    promo_starts_on     DATE,
    promo_ends_on       DATE,
    availability        TEXT NOT NULL CHECK (availability IN ('in_stock', 'out_of_stock', 'unknown')),
    published_ts        TIMESTAMPTZ NOT NULL,
    fetched_ts          TIMESTAMPTZ NOT NULL,
    source_url          TEXT NOT NULL,
    run_id              INT NOT NULL REFERENCES ingestion_runs(id),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, retailer_product_id)
);

-- Immutable; identical publications deduplicate via the unique constraint.
CREATE TABLE price_observations (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer_product_id INT NOT NULL REFERENCES retailer_products(id),
    store_id            INT NOT NULL REFERENCES stores(id),
    currency            CHAR(3) NOT NULL DEFAULT 'MKD',
    price_current       NUMERIC(12,2) NOT NULL CHECK (price_current >= 0),
    unit_price          NUMERIC(12,2) CHECK (unit_price IS NULL OR unit_price >= 0),
    unit_label          TEXT,
    regular_price       NUMERIC(12,2) CHECK (regular_price IS NULL OR regular_price >= 0),
    discount_price      NUMERIC(12,2) CHECK (discount_price IS NULL OR discount_price >= 0),
    discount_pct        NUMERIC(5,2)  CHECK (discount_pct IS NULL OR (discount_pct >= 0 AND discount_pct <= 100)),
    promo_type          TEXT,
    promo_starts_on     DATE,
    promo_ends_on       DATE,
    availability        TEXT NOT NULL CHECK (availability IN ('in_stock', 'out_of_stock', 'unknown')),
    published_ts        TIMESTAMPTZ NOT NULL,
    fetched_ts          TIMESTAMPTZ NOT NULL,
    source_url          TEXT NOT NULL,
    raw_snapshot_id     BIGINT REFERENCES raw_snapshots(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (retailer_product_id, store_id, published_ts, price_current)
);

CREATE INDEX idx_observations_product_store
    ON price_observations (retailer_product_id, store_id, published_ts DESC);

CREATE TABLE promotions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer_product_id INT NOT NULL REFERENCES retailer_products(id),
    store_id            INT NOT NULL REFERENCES stores(id),
    promo_type          TEXT NOT NULL,
    discount_pct        NUMERIC(5,2) CHECK (discount_pct IS NULL OR (discount_pct >= 0 AND discount_pct <= 100)),
    starts_on           DATE,
    ends_on             DATE,
    source_url          TEXT NOT NULL,
    run_id              INT NOT NULL REFERENCES ingestion_runs(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (retailer_product_id, store_id, promo_type, starts_on, ends_on)
);

-- Reference data: Vero retailer + stores from the validated 2026-10-28 index page
-- (see docs/research/retailer-sources.md and tests/fixtures/vero/index.html).
INSERT INTO retailers (slug, name) VALUES ('vero', 'Vero') ON CONFLICT DO NOTHING;

INSERT INTO stores (retailer_id, external_key, name, address, city)
SELECT r.id, v.ext, v.nm, v.addr, v.city
FROM (VALUES
    ('89',  'ВЕРО 1',  'Бул. Јане Сандански бр.111 – Аеродром',                    'Аеродром'),
    ('91',  'ВЕРО 2',  'Бул. Митрополит Теодосиј Гологанов бр.76 – Карпош',        'Карпош'),
    ('94',  'ВЕРО 3',  'Ул. Видое Смилевски Бато бр.7 – Тетово',                   'Тетово'),
    ('97',  'ВЕРО 4',  'Ул. Игњат Атанасовски бр.15 – Битола',                     'Битола'),
    ('100', 'ВЕРО 5',  'Бул. Митрополит Теодосиј Гологанов бр.26 – Центар',        'Центар'),
    ('102', 'ВЕРО 6',  'Ул. Широк сокак бр. 44а – Битола',                         'Битола'),
    ('104', 'ВЕРО 7',  'Ул. Кеј 13 Ноември ГТЦ/ЛОКАЛ 443 – Центар',                'Центар'),
    ('106', 'ВЕРО 8',  'Ул. Џон Кенеди бр.2 – Чаир',                               'Чаир'),
    ('108', 'ВЕРО 9',  'Бул. Кочо Рацин бр.1 – Центар',                            'Центар'),
    ('114', 'ВЕРО 10', 'Бул. Борис Трајковски бр.13 - Кисела Вода',                'Кисела Вода'),
    ('116', 'ВЕРО 11', 'Ул.113 бр.3 – Тетово',                                     'Тетово'),
    ('120', 'ВЕРО 12', 'Ул. Манапо бр.3 – Карпош',                                 'Карпош'),
    ('162', 'ВЕРО 13', 'Бул. Св. Кирил и Методиј бр.3 – Центар',                   'Центар'),
    ('164', 'ВЕРО 14', 'Ул. ЈНА бр.106 – Куманово',                                'Куманово'),
    ('124', 'ЏАМБО 1', 'Бул. Кочо Рацин бр.1 – Центар',                            'Центар'),
    ('119', 'ЏАМБО 2', 'Ул. Игњат Атанасовски бр.25 – Битола',                     'Битола'),
    ('168', 'ЏАМБО 3', 'Ул.Граничен премин Богородица бр.8 Богородица - Гевгелија', 'Гевгелија')
) AS v(ext, nm, addr, city)
JOIN retailers r ON r.slug = 'vero'
ON CONFLICT (retailer_id, external_key) DO NOTHING;

COMMIT;
