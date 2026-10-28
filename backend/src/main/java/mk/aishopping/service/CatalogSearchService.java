package mk.aishopping.service;

import mk.aishopping.model.ApiModels.HealthResponse;
import mk.aishopping.model.ApiModels.OfferDto;
import mk.aishopping.model.ApiModels.OfferSearchFilter;
import mk.aishopping.model.ApiModels.ProductComparisonDto;
import mk.aishopping.model.ApiModels.ProductHistoryResponse;
import mk.aishopping.model.ApiModels.ReviewQueueItemDto;
import mk.aishopping.model.ApiModels.SearchResponse;
import mk.aishopping.model.ApiModels.StoreDto;
import mk.aishopping.repository.PostgresCatalogRepository;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class CatalogSearchService {

    private final OpenSearchClient openSearchClient;
    private final PostgresCatalogRepository postgresRepository;

    public CatalogSearchService(
            OpenSearchClient openSearchClient,
            PostgresCatalogRepository postgresRepository
    ) {
        this.openSearchClient = openSearchClient;
        this.postgresRepository = postgresRepository;
    }

    public HealthResponse getHealth() {
        boolean dbUp = postgresRepository.isDatabaseHealthy();
        Map<String, Long> counts = new LinkedHashMap<>();
        if (dbUp) {
            counts.putAll(postgresRepository.getTableCounts());
        }

        boolean osUp = false;
        try {
            long osStores = openSearchClient.countIndex("stores");
            long osOffers = openSearchClient.countIndex("offers");
            long osProducts = openSearchClient.countIndex("products");
            if (osStores >= 0 && osOffers >= 0 && osProducts >= 0) {
                osUp = true;
                counts.put("opensearch_stores", osStores);
                counts.put("opensearch_offers", osOffers);
                counts.put("opensearch_products", osProducts);
            }
        } catch (Exception ignored) {
            osUp = false;
        }

        String status = dbUp ? "UP" : "DOWN";
        String dbStatus = dbUp ? "UP" : "DOWN";
        String osStatus = osUp ? "UP" : "FALLBACK_POSTGRESQL";
        String activeEngine = osUp ? "opensearch" : "postgresql_fallback";

        return new HealthResponse(status, dbStatus, osStatus, activeEngine, counts);
    }

    public SearchResponse<StoreDto> getStores(String retailer, String city) {
        if (openSearchClient.isHealthyAndPopulated()) {
            try {
                return openSearchClient.searchStores(retailer, city);
            } catch (Exception ignored) {
                // Fall back to authoritative PostgreSQL store catalog
            }
        }
        return postgresRepository.findStores(retailer, city);
    }

    public SearchResponse<OfferDto> searchOffers(OfferSearchFilter filter) {
        if (openSearchClient.isHealthyAndPopulated()) {
            try {
                return openSearchClient.searchOffers(filter);
            } catch (Exception ignored) {
                // Fall back to authoritative PostgreSQL offers_current query
            }
        }
        return postgresRepository.searchOffers(filter);
    }

    public SearchResponse<ProductComparisonDto> compareProducts(String q, int minRetailers, int page, int size) {
        if (openSearchClient.isHealthyAndPopulated()) {
            try {
                return openSearchClient.searchProductComparisons(q, minRetailers, page, size);
            } catch (Exception ignored) {
                // Fall back to authoritative PostgreSQL comparison query
            }
        }
        return postgresRepository.compareProducts(q, minRetailers, page, size);
    }

    public Optional<ProductHistoryResponse> getProductHistory(int canonicalProductId) {
        return postgresRepository.getProductHistory(canonicalProductId);
    }

    public List<ReviewQueueItemDto> getReviewQueue(int limit) {
        return postgresRepository.getReviewQueue(limit);
    }
}
