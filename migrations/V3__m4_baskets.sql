-- V3__m4_baskets.sql — M4 schema: persisted shopping lists and basket line items
-- with unit/quantity scaling and canonical/retailer product references.

SET client_encoding = 'UTF8';

BEGIN;

CREATE TABLE shopping_lists (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL CHECK (btrim(name) <> ''),
    city_filter TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE shopping_list_items (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shopping_list_id     BIGINT NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
    canonical_product_id INT REFERENCES canonical_products(id),
    retailer_product_id  INT REFERENCES retailer_products(id),
    item_label           TEXT,
    quantity             NUMERIC(12,3) NOT NULL DEFAULT 1.000 CHECK (quantity > 0),
    unit                 TEXT NOT NULL DEFAULT 'pack'
                         CHECK (unit IN ('pack', 'pcs', 'g', 'kg', 'ml', 'l')),
    position             INT NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (canonical_product_id IS NOT NULL OR retailer_product_id IS NOT NULL)
);

CREATE INDEX idx_shopping_list_items_list
    ON shopping_list_items (shopping_list_id, position, id);

COMMIT;
