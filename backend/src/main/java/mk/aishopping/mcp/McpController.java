package mk.aishopping.mcp;

import mk.aishopping.mcp.McpProtocolModels.McpRequest;
import mk.aishopping.mcp.McpProtocolModels.McpResponse;
import mk.aishopping.mcp.McpProtocolModels.McpToolCallResult;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/mcp")
public class McpController {

    private static final String PROTOCOL_VERSION = "2024-11-05";
    private static final String SERVER_NAME = "ai-shopping-mcp-server";
    private static final String SERVER_VERSION = "0.5.0";

    private final McpToolRegistry toolRegistry;

    public McpController(McpToolRegistry toolRegistry) {
        this.toolRegistry = toolRegistry;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> handleJsonRpc(@RequestBody(required = false) McpRequest request) {
        if (request == null || request.method() == null) {
            return ResponseEntity.badRequest().body(
                    McpResponse.error(null, -32600, "Invalid Request: missing method", null)
            );
        }

        Object id = request.id();
        String method = request.method().trim();

        // Notification: client does not expect a response
        if (id == null && method.startsWith("notifications/")) {
            return ResponseEntity.noContent().build();
        }

        try {
            return switch (method) {
                case "initialize" -> ResponseEntity.ok(McpResponse.success(id, handleInitialize(request.params())));
                case "notifications/initialized" -> ResponseEntity.noContent().build();
                case "ping" -> ResponseEntity.ok(McpResponse.success(id, Map.of()));
                case "tools/list" -> ResponseEntity.ok(McpResponse.success(id, Map.of("tools", toolRegistry.listTools())));
                case "tools/call" -> ResponseEntity.ok(McpResponse.success(id, handleToolCall(request.params())));
                default -> ResponseEntity.ok(McpResponse.error(id, -32601, "Method not found: " + method, null));
            };
        } catch (IllegalArgumentException e) {
            return ResponseEntity.ok(McpResponse.error(id, -32602, "Invalid params: " + e.getMessage(), null));
        } catch (Exception e) {
            return ResponseEntity.ok(McpResponse.error(id, -32603, "Internal error: " + e.getMessage(), null));
        }
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> serverInfo() {
        Map<String, Object> info = new LinkedHashMap<>();
        info.put("server", SERVER_NAME);
        info.put("version", SERVER_VERSION);
        info.put("protocolVersion", PROTOCOL_VERSION);
        info.put("transport", "streamable-http");
        info.put("endpoint", "/mcp");
        info.put("sseEndpoint", "/mcp/sse");
        info.put("capabilities", Map.of("tools", Map.of("listChanged", false)));
        return info;
    }

    @GetMapping(value = "/sse", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter sseEndpoint() {
        SseEmitter emitter = new SseEmitter(60_000L);
        try {
            emitter.send(SseEmitter.event().name("endpoint").data("/mcp"));
        } catch (IOException e) {
            emitter.completeWithError(e);
        }
        return emitter;
    }

    private Map<String, Object> handleInitialize(Map<String, Object> params) {
        Map<String, Object> res = new LinkedHashMap<>();
        res.put("protocolVersion", PROTOCOL_VERSION);
        res.put("capabilities", Map.of("tools", Map.of("listChanged", false)));
        res.put("serverInfo", Map.of(
                "name", SERVER_NAME,
                "version", SERVER_VERSION
        ));
        return res;
    }

    @SuppressWarnings("unchecked")
    private McpToolCallResult handleToolCall(Map<String, Object> params) {
        if (params == null || !params.containsKey("name")) {
            throw new IllegalArgumentException("'name' is required for tools/call");
        }
        String toolName = (String) params.get("name");
        Map<String, Object> arguments = params.containsKey("arguments") && params.get("arguments") instanceof Map<?, ?> m
                ? (Map<String, Object>) m
                : Map.of();

        return toolRegistry.callTool(toolName, arguments);
    }
}
