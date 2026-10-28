-- V2__m2_identity.sql — M2 schema: canonical product identity, product_matches,
-- and second-source retailer/store reference data (Stokomak + Zito) per ADR-0003.

SET client_encoding = 'UTF8';

BEGIN;

CREATE TABLE canonical_products (
    id                INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_key     TEXT NOT NULL UNIQUE,
    canonical_name    TEXT NOT NULL,
    normalized_tokens TEXT NOT NULL,
    normalized_size   TEXT,
    quantity_value    NUMERIC(12,3) CHECK (quantity_value IS NULL OR quantity_value > 0),
    quantity_unit     TEXT,
    pack_count        INT NOT NULL DEFAULT 1 CHECK (pack_count >= 1),
    gtin              TEXT UNIQUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ADR-0003: Product identity is distinct from substitution/equivalence.
-- Only review_status IN ('auto_accepted', 'approved') is treated as verified identity
-- in cross-retailer comparisons; ambiguous Stage-2 candidates sit in 'pending_review'.
CREATE TABLE product_matches (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer_product_id  INT NOT NULL REFERENCES retailer_products(id),
    canonical_product_id INT NOT NULL REFERENCES canonical_products(id),
    method               TEXT NOT NULL
                         CHECK (method IN ('gtin_exact', 'normalized_exact_v1', 'candidate_token_size_v1', 'manual_approved')),
    confidence           NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    review_status        TEXT NOT NULL DEFAULT 'auto_accepted'
                         CHECK (review_status IN ('auto_accepted', 'pending_review', 'approved', 'rejected')),
    evidence             JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewed_by          TEXT,
    reviewed_at          TIMESTAMPTZ,
    review_notes         TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (retailer_product_id, canonical_product_id)
);

-- At most one active/verified canonical identity per retailer_product_id.
CREATE UNIQUE INDEX uq_product_matches_active_retailer_product
    ON product_matches (retailer_product_id)
    WHERE review_status IN ('auto_accepted', 'approved');

CREATE INDEX idx_product_matches_canonical
    ON product_matches (canonical_product_id, review_status);

-- Reference data: Stokomak + Zito retailers and stores from validated 2026-10-28 selectors.
INSERT INTO retailers (slug, name) VALUES
    ('stokomak', 'Stokomak'),
    ('zito',     'Zito')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO stores (retailer_id, external_key, name, address, city)
SELECT r.id, v.ext, v.nm, v.addr, v.city
FROM (VALUES
    ('1', 'КИСЕЛА ВОДА', NULL, NULL),
    ('2', 'КУМАНОВО 2', NULL, NULL),
    ('3', 'КАРПОШ 2', NULL, NULL),
    ('4', 'АВТОКОМАНДА', NULL, NULL),
    ('5', 'БУТЕЛ', NULL, NULL),
    ('6', 'АЕРОДРОМ 2', NULL, NULL),
    ('7', 'ТАФТАЛИЏЕ', NULL, NULL),
    ('8', 'МЛЕЧЕН', NULL, NULL),
    ('9', 'ОХРИД 1', NULL, NULL),
    ('10', 'КУМАНОВО 3', NULL, NULL),
    ('11', 'АЕРОДРОМ 1', NULL, NULL),
    ('12', 'КАРПОШ 4', NULL, NULL),
    ('13', 'СИНГЕЛИЧ', NULL, NULL),
    ('14', 'ЦЕНТАР', NULL, NULL),
    ('16', 'КАПИШТЕЦ', NULL, NULL),
    ('17', 'ЃОРЧЕ ПЕТРОВ 2', NULL, NULL),
    ('18', 'ДРАЧЕВО', NULL, NULL),
    ('19', 'КУМАНОВО 1', NULL, NULL),
    ('20', 'ВОДЊАНСКА', NULL, NULL),
    ('21', 'БУЊАКОВЕЦ', NULL, NULL),
    ('22', 'НОВО ЛИСИЧЕ', NULL, NULL),
    ('23', 'ХИПОДРОМ', NULL, NULL),
    ('24', 'РАСАДНИК', NULL, NULL),
    ('25', 'НОВО ЛИСИЧЕ 2', NULL, NULL),
    ('26', 'ТОПАНСКО ПОЛЕ', NULL, NULL),
    ('27', 'ЧАИР', NULL, NULL),
    ('28', 'КОЗЛЕ', NULL, NULL),
    ('29', 'МИЧУРИН', NULL, NULL),
    ('30', 'ШТИП', NULL, NULL),
    ('31', 'ГОРЧЕ ДЕКСИОН', NULL, NULL),
    ('32', 'ТЕТОВО', NULL, NULL),
    ('33', 'СЕВЕР', NULL, NULL),
    ('34', 'РАДИШАНИ', NULL, NULL),
    ('35', 'ЧЕНТО 2', NULL, NULL),
    ('36', 'ИЛИНДЕН', NULL, NULL),
    ('37', 'КУМАНОВО 4', NULL, NULL),
    ('38', 'ПРИЛЕП', NULL, NULL),
    ('39', 'КОЧАНИ', NULL, NULL),
    ('40', 'ТЕТОВО 2', NULL, NULL),
    ('41', 'ВЕЛЕС', NULL, NULL),
    ('42', 'НЕГОТИНО', NULL, NULL),
    ('43', 'ВЛАЕ', NULL, NULL),
    ('44', 'РЕСЕН', NULL, NULL),
    ('45', 'ПРОБИШТИП', NULL, NULL),
    ('46', 'ШТИП 2', NULL, NULL),
    ('47', 'ГЕВГЕЛИЈА', NULL, NULL),
    ('48', 'СТРУМИЦА', NULL, NULL),
    ('49', 'ГОСТИВАР', NULL, NULL),
    ('50', 'БИТОЛА', NULL, NULL),
    ('51', 'ОХРИД 2', NULL, NULL),
    ('52', 'РАДОВИШ', NULL, NULL),
    ('53', 'БИТОЛА 2', NULL, NULL),
    ('54', 'КИЧЕВО', NULL, NULL),
    ('55', 'СТРУМИЦА 2', NULL, NULL),
    ('56', 'КАВАДАРЦИ', NULL, NULL),
    ('57', 'СТРУГА', NULL, NULL),
    ('58', 'ДЕЛЧЕВО', NULL, NULL),
    ('59', 'ВИНИЦА', NULL, NULL),
    ('60', 'ТЕТОВО 3', NULL, NULL),
    ('61', 'КРИВА ПАЛАНКА', NULL, NULL),
    ('62', 'ПРИЛЕП 2', NULL, NULL),
    ('63', 'КИСЕЛА ВОДА 2', NULL, NULL),
    ('64', 'ПЕТРОВЕЦ', NULL, NULL),
    ('65', 'ВЕЛЕС 2', NULL, NULL),
    ('66', 'НОВОСЕЛСКИ ПАТ', NULL, NULL),
    ('67', 'СВЕТИ НИКОЛЕ', NULL, NULL),
    ('68', 'БЕРОВО', NULL, NULL),
    ('69', 'КРАТОВО', NULL, NULL),
    ('70', 'ДЕБАР', NULL, NULL),
    ('71', 'ШТИП 3', NULL, NULL),
    ('72', 'ДРАЧЕВО 2', NULL, NULL),
    ('73', 'ВЛАЕ 2 АЛЕКСАНДРИЈА', NULL, NULL),
    ('74', 'ЧАИР 2', NULL, NULL),
    ('75', 'СТРУГА 2', NULL, NULL),
    ('76', 'КУМАНОВО 5', NULL, NULL),
    ('77', 'КОЧАНИ 2', NULL, NULL),
    ('78', 'МАРКЕТ МАЏАРИ', NULL, NULL),
    ('79', 'СТРУМИЦА 3', NULL, NULL),
    ('80', 'МАК. КАМЕНИЦА', NULL, NULL),
    ('81', 'ЈУЖЕН БУЛЕВАР', NULL, NULL),
    ('82', 'МАРКЕТ ЗЛОКУЌАНИ', NULL, NULL)
) AS v(ext, nm, addr, city)
JOIN retailers r ON r.slug = 'stokomak'
ON CONFLICT (retailer_id, external_key) DO NOTHING;

INSERT INTO stores (retailer_id, external_key, name, address, city)
SELECT r.id, v.ext, v.nm, v.addr, v.city
FROM (VALUES
    ('2', '2 Трговски - Велес', NULL, 'Велес'),
    ('3', '3 Струмица 4', NULL, NULL),
    ('4', '4 Пазар - Кочани', NULL, 'Кочани'),
    ('5', '5 Делчево 2', NULL, NULL),
    ('6', '6 Куманово - Трговски', NULL, 'Трговски'),
    ('7', '7 Интернат - Велес', NULL, 'Велес'),
    ('8', '8 Бутел1 - Скопје', NULL, 'Скопје'),
    ('9', '9 Жито Ване - Велес', NULL, 'Велес'),
    ('10', '10 Жито Ване Кат', NULL, NULL),
    ('11', '11 Ѓорче - Скопје', NULL, 'Скопје'),
    ('12', '12 Демир капија', NULL, NULL),
    ('13', '13 Центар ЗОИЛ - Скопје', NULL, 'Скопје'),
    ('14', '14 Мичурин - Скопје', NULL, 'Скопје'),
    ('15', '15 Соколана - Велес', NULL, 'Велес'),
    ('16', '16 Центар - Велес', NULL, 'Велес'),
    ('17', '17 Автобуска - Кочани', NULL, 'Кочани'),
    ('18', '18 Баумаркет - Скопје', NULL, 'Скопје'),
    ('19', '19 Фонтана - Велес', NULL, 'Велес'),
    ('20', '20 Багремче - Велес', NULL, 'Велес'),
    ('21', '21 Градско', NULL, NULL),
    ('22', '22 Илинден - Скопје', NULL, 'Скопје'),
    ('23', '23 Рид - Прилеп', NULL, 'Прилеп'),
    ('24', '24 Штип Сењак', NULL, NULL),
    ('25', '25 Виница', NULL, NULL),
    ('26', '26 Неготино', NULL, NULL),
    ('27', '27 Делчево', NULL, NULL),
    ('28', '28 Росоман', NULL, NULL),
    ('29', '29 Општина - Велес', NULL, 'Велес'),
    ('30', '30 Струмица 1', NULL, NULL),
    ('31', '95 Кавадарци 2', NULL, NULL),
    ('32', '32 Поток - Тетово', NULL, 'Тетово'),
    ('33', '33 Валандово', NULL, NULL),
    ('34', '34 Гостивар', NULL, NULL),
    ('35', '35 Ново Лисиче - Скопје', NULL, 'Скопје'),
    ('36', '96 К.Вода Расадник 2', NULL, NULL),
    ('37', '37 Градски Саат - Велес', NULL, 'Велес'),
    ('38', '38 Аеродром Пазар - Скопје', NULL, 'Скопје'),
    ('39', '39 Кисела Вода 2 - Скопје', NULL, 'Скопје'),
    ('40', '40 Бутел2 - Скопје', NULL, 'Скопје'),
    ('41', '41 Кеј - Прилеп', NULL, 'Прилеп'),
    ('42', '42 Облешево', NULL, NULL),
    ('43', '43 Железара - Скопје', NULL, 'Скопје'),
    ('44', '44 Драчево1 - Скопје', NULL, 'Скопје'),
    ('45', '45 Превалец', NULL, NULL),
    ('46', '46 Аеродром Тобако - Скопје', NULL, 'Скопје'),
    ('47', '47 Аеродром Капитол - Скопје', NULL, 'Скопје'),
    ('48', '48 Влае - Скопје', NULL, 'Скопје'),
    ('49', '49 Чашка', NULL, NULL),
    ('50', '50 Влез - Кочани', NULL, 'Кочани'),
    ('51', '51 КиМ - Велес', NULL, 'Велес'),
    ('52', '52 Касарна - Битола', NULL, 'Битола'),
    ('53', '53 Градинка - Велес', NULL, 'Велес'),
    ('54', '54 Брвеница - Тетово', NULL, 'Тетово'),
    ('55', '55 Којник - Велес', NULL, 'Велес'),
    ('56', '56 Аеродром Поликлиника -Скопје', NULL, NULL),
    ('57', '57-Петровец - Скопје', NULL, 'Скопје'),
    ('58', '58 Битола-2', NULL, NULL),
    ('59', '59 Куманово', NULL, NULL),
    ('60', '60 Македонска Каменица', NULL, NULL),
    ('61', '61 Автокоманда - Скопје', NULL, 'Скопје'),
    ('62', '62 Гимназија', NULL, NULL),
    ('63', '63 Гимназија-Дом', NULL, NULL),
    ('64', '64 Битола-3', NULL, NULL),
    ('65', '65 Илинден 2', NULL, NULL),
    ('66', '66 Волково - Скопје', NULL, 'Скопје'),
    ('67', '67 Ламели Кичево', NULL, NULL),
    ('68', '68 Девеана Кичево', NULL, NULL),
    ('69', '69 жито Гостивар Автобуска', NULL, NULL),
    ('70', '70 Гевгелија', NULL, NULL),
    ('71', '71 Жито Свети Николе Автобуска', NULL, NULL),
    ('72', '72 Жито Кочани Излез', NULL, NULL),
    ('73', '73 Жито ПробиШтип Автобуска', NULL, NULL),
    ('74', '74 Жито Струмица 2', NULL, NULL),
    ('75', '75 Жито Штип 2 Влез', NULL, NULL),
    ('76', '76 Жито Штип Центар', NULL, NULL),
    ('78', '78 Ла Фамилиа Велес', NULL, NULL),
    ('79', '79 Ла Фамилиа Центар', NULL, NULL),
    ('80', '80 Ла Фамилиа ЕАСТ ГАТЕ', NULL, NULL),
    ('81', '81 Ла Фамилиа Кавадарци', NULL, NULL),
    ('82', '82 Жито Којник', NULL, NULL),
    ('83', '83 Жито Дос Велес', NULL, NULL),
    ('84', '84 Куманово 3', NULL, NULL),
    ('85', '85 Струмица 3', NULL, NULL),
    ('86', '86 Струга', NULL, NULL),
    ('87', '87 Охрид', NULL, NULL),
    ('88', '88 Ла Фамилија Охрид', NULL, NULL),
    ('89', '89 Штип градинка', NULL, NULL),
    ('90', '90 Чашка', NULL, NULL),
    ('91', '91 Тетово тетовчанка', NULL, NULL),
    ('92', '92 Тетово општина', NULL, NULL),
    ('93', '93 Бауман', NULL, NULL),
    ('94', '94 Кавадарци', NULL, NULL),
    ('95', '95 Драчево 2', NULL, NULL),
    ('96', '96 Радовиш', NULL, NULL)
) AS v(ext, nm, addr, city)
JOIN retailers r ON r.slug = 'zito'
ON CONFLICT (retailer_id, external_key) DO NOTHING;

COMMIT;
