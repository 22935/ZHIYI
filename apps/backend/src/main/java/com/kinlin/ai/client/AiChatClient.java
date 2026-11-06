package com.kinlin.ai.client;

import com.kinlin.ai.dto.ChatResponse;

import java.util.List;
import java.util.Map;

/**
 * What the Java platform needs from the Python conversational AI capability.
 *
 * <p>Covers text chat (the {@code /ai/chat/**} family).
 * Implementations own endpoint paths, serialization, timeouts and transport error
 * classification; callers only see {@link com.kinlin.ai.dto.ChatResponse} or a
 * {@link PlatformAiClientException}.</p>
 */
public interface AiChatClient {

    ChatResponse sendText(AiChatCommand command);

    /**
     * Text chat invocation with optional runtime model overrides. Null/blank optional
     * fields are not sent upstream.
     */
    record AiChatCommand(
            String text,
            String roleId,
            List<Map<String, String>> context,
            String contextId,
            String model,
            String baseUrl,
            String apiKey,
            String thinkingMode,
            String toolMode
    ) {
    }
}
