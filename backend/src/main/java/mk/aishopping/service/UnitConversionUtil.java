package mk.aishopping.service;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class UnitConversionUtil {

    private UnitConversionUtil() {}

    public static String normalizeUnit(String rawUnit) {
        if (rawUnit == null || rawUnit.isBlank()) {
            return "pack";
        }
        String u = rawUnit.trim().toLowerCase();
        return switch (u) {
            case "g", "gr", "gram", "grams", "гр", "грам" -> "g";
            case "kg", "kgr", "kilogram", "kilograms", "кг", "кгр" -> "kg";
            case "ml", "milliliter", "milliliters", "мл" -> "ml";
            case "l", "lt", "liter", "liters", "л", "литар" -> "l";
            case "pcs", "pc", "piece", "pieces", "бр", "број", "пар", "парче" -> "pcs";
            default -> "pack";
        };
    }

    public static String dimensionOf(String normalizedUnit) {
        return switch (normalizedUnit) {
            case "g", "kg" -> "mass";
            case "ml", "l" -> "volume";
            default -> "count";
        };
    }

    public static BigDecimal toBaseAmount(BigDecimal quantity, String normalizedUnit) {
        BigDecimal safeQty = (quantity == null || quantity.compareTo(BigDecimal.ZERO) <= 0)
                ? BigDecimal.ONE
                : quantity;
        return switch (normalizedUnit) {
            case "kg", "l" -> safeQty.multiply(BigDecimal.valueOf(1000));
            default -> safeQty;
        };
    }

    /**
     * Deterministically computes how many SKU packs are needed to satisfy the requested quantity and unit.
     *
     * @param requestedQty  user requested quantity (e.g. 1, 2, 1000, 1.5)
     * @param requestedUnit user requested unit ("pack", "pcs", "g", "kg", "ml", "l")
     * @param skuQtyValue   canonical product's per-unit quantity_value in base unit (g or ml), nullable
     * @param skuQtyUnit    canonical product's quantity_unit ("g" or "ml"), nullable
     * @param skuPackCount  canonical product's pack_count (default 1)
     * @return integer number of SKU packs needed (>= 1)
     */
    public static int computePacksNeeded(
            BigDecimal requestedQty,
            String requestedUnit,
            BigDecimal skuQtyValue,
            String skuQtyUnit,
            int skuPackCount
    ) {
        BigDecimal safeReqQty = (requestedQty == null || requestedQty.compareTo(BigDecimal.ZERO) <= 0)
                ? BigDecimal.ONE
                : requestedQty;
        String normReqUnit = normalizeUnit(requestedUnit);
        String reqDim = dimensionOf(normReqUnit);

        if ("count".equals(reqDim) || skuQtyValue == null || skuQtyValue.compareTo(BigDecimal.ZERO) <= 0 || skuQtyUnit == null) {
            return Math.max(1, safeReqQty.setScale(0, RoundingMode.CEILING).intValueExact());
        }

        String normSkuUnit = normalizeUnit(skuQtyUnit);
        String skuDim = dimensionOf(normSkuUnit);
        if (!reqDim.equals(skuDim)) {
            // Incompatible dimensions (e.g. requested 'g' for a 'ml' beverage) -> treat requestedQty as pack count
            return Math.max(1, safeReqQty.setScale(0, RoundingMode.CEILING).intValueExact());
        }

        int safePackCount = Math.max(1, skuPackCount);
        BigDecimal requestedBase = toBaseAmount(safeReqQty, normReqUnit);
        BigDecimal perSkuBase = toBaseAmount(skuQtyValue, normSkuUnit).multiply(BigDecimal.valueOf(safePackCount));
        if (perSkuBase.compareTo(BigDecimal.ZERO) <= 0) {
            return 1;
        }

        BigDecimal packs = requestedBase.divide(perSkuBase, 0, RoundingMode.CEILING);
        return Math.max(1, packs.intValueExact());
    }
}
