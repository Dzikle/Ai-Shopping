package mk.aishopping.controller;

import mk.aishopping.model.BasketModels.BasketOptimizationResponse;
import mk.aishopping.model.BasketModels.BasketOptimizeRequest;
import mk.aishopping.model.BasketModels.CreateShoppingListRequest;
import mk.aishopping.model.BasketModels.ShoppingListDto;
import mk.aishopping.service.BasketOptimizerService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/baskets")
public class BasketController {

    private final BasketOptimizerService basketService;

    public BasketController(BasketOptimizerService basketService) {
        this.basketService = basketService;
    }

    @PostMapping("/optimize")
    public ResponseEntity<?> optimizeAdHocBasket(@RequestBody BasketOptimizeRequest request) {
        try {
            BasketOptimizationResponse resp = basketService.optimizeBasket(request);
            return ResponseEntity.ok(resp);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @PostMapping("/lists")
    public ResponseEntity<?> createShoppingList(@RequestBody CreateShoppingListRequest request) {
        try {
            ShoppingListDto created = basketService.createShoppingList(request);
            return ResponseEntity.status(HttpStatus.CREATED).body(created);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @GetMapping("/lists/{listId}")
    public ResponseEntity<ShoppingListDto> getShoppingList(@PathVariable long listId) {
        return basketService.getShoppingList(listId)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/lists/{listId}/optimize")
    public ResponseEntity<BasketOptimizationResponse> optimizeSavedShoppingList(
            @PathVariable long listId,
            @RequestBody(required = false) BasketOptimizeRequest overrides
    ) {
        return basketService.optimizeSavedList(listId, overrides)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
