package mk.aishopping.mcp;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;
import java.util.Map;

public final class McpProtocolModels {

    private McpProtocolModels() {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record McpRequest(
            String jsonrpc,
            Object id,
            String method,
            Map<String, Object> params
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record McpResponse(
            String jsonrpc,
            Object id,
            Object result,
            McpError error
    ) {
        public static McpResponse success(Object id, Object result) {
            return new McpResponse("2.0", id, result, null);
        }

        public static McpResponse error(Object id, int code, String message, Object data) {
            return new McpResponse("2.0", id, null, new McpError(code, message, data));
        }
    }

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record McpError(
            int code,
            String message,
            Object data
    ) {}

    public record McpToolDefinition(
            String name,
            String description,
            Map<String, Object> inputSchema
    ) {}

    public record McpToolCallResult(
            List<McpContentBlock> content,
            boolean isError
    ) {}

    public record McpContentBlock(
            String type,
            String text
    ) {}
}
