package mk.aishopping.controller;

import mk.aishopping.model.ApiModels.HealthResponse;
import mk.aishopping.model.ApiModels.OfferDto;
import mk.aishopping.model.ApiModels.OfferSearchFilter;
import mk.aishopping.model.ApiModels.ProductComparisonDto;
import mk.aishopping.model.ApiModels.ProductHistoryResponse;
import mk.aishopping.model.ApiModels.ReviewQueueItemDto;
import mk.aishopping.model.ApiModels.SearchResponse;
import mk.aishopping.model.ApiModels.StoreDto;
import mk.aishopping.service.CatalogSearchService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.List;

@RestController
@RequestMapping("/api/v1")
public class CatalogController {

    private final CatalogSearchService searchService;

    public CatalogController(CatalogSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping("/health")
    public HealthResponse health() {
        return searchService.getHealth();
    }

    @GetMapping("/stores")
    public SearchResponse<StoreDto> stores(
            @RequestParam(required = false) String retailer,
            @RequestParam(required = false) String city
    ) {
        return searchService.getStores(retailer, city);
    }

    @GetMapping("/offers/search")
    public SearchResponse<OfferDto> searchOffers(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String retailer,
            @RequestParam(required = false) String storeKey,
            @RequestParam(required = false) String category,
            @RequestParam(defaultValue = "false") boolean inStockOnly,
            @RequestParam(defaultValue = "false") boolean promoOnly,
            @RequestParam(required = false) BigDecimal minPrice,
            @RequestParam(required = false) BigDecimal maxPrice,
            @RequestParam(defaultValue = "price_asc") String sort,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size
    ) {
        OfferSearchFilter filter = new OfferSearchFilter(
                q, retailer, storeKey, category, inStockOnly, promoOnly, minPrice, maxPrice, sort, page, size
        );
        return searchService.searchOffers(filter);
    }

    @GetMapping("/products/compare")
    public SearchResponse<ProductComparisonDto> compareProducts(
            @RequestParam(required = false) String q,
            @RequestParam(defaultValue = "2") int minRetailers,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size
    ) {
        return searchService.compareProducts(q, minRetailers, page, size);
    }

    @GetMapping("/products/{canonicalId}/history")
    public ResponseEntity<ProductHistoryResponse> productHistory(@PathVariable int canonicalId) {
        return searchService.getProductHistory(canonicalId)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/matches/review-queue")
    public List<ReviewQueueItemDto> reviewQueue(@RequestParam(defaultValue = "25") int limit) {
        return searchService.getReviewQueue(limit);
    }
}
