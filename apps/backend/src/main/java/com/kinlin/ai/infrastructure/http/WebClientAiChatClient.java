package com.kinlin.ai.infrastructure.http;

import com.kinlin.ai.client.AiChatClient;
import com.kinlin.ai.dto.ChatResponse;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;

/** WebClient implementation of the chat capability ({@code /ai/chat/text}). */
@Component
public class WebClientAiChatClient implements AiChatClient {

    private final PlatformAiTransport transport;

    public WebClientAiChatClient(PlatformAiTransport transport) {
        this.transport = transport;
    }

    @Override
    public ChatResponse sendText(AiChatCommand command) {
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("text", command.text());
        if (command.roleId() != null) {
            requestBody.put("role_id", command.roleId());
        }
        if (command.context() != null) {
            requestBody.put("context", command.context());
        }
        if (command.contextId() != null) {
            requestBody.put("context_id", command.contextId());
        }
        if (command.model() != null && !command.model().isBlank()) {
            requestBody.put("model", command.model());
        }
        if (command.baseUrl() != null && !command.baseUrl().isBlank()) {
            requestBody.put("base_url", command.baseUrl());
        }
        if (command.apiKey() != null && !command.apiKey().isBlank()) {
            requestBody.put("api_key", command.apiKey());
        }
        if (command.thinkingMode() != null && !command.thinkingMode().isBlank()) {
            requestBody.put("thinking_mode", command.thinkingMode());
        }
        if (command.toolMode() != null && !command.toolMode().isBlank()) {
            requestBody.put("tool_mode", command.toolMode());
        }
        return transport.postJson("/ai/chat/text", requestBody, ChatResponse.class);
    }
}
