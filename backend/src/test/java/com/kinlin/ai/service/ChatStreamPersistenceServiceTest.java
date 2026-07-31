package com.kinlin.ai.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;

import java.util.Map;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class ChatStreamPersistenceServiceTest {

    @Test
    void persistsFinalContentAndMetricsWithoutRawReasoning() {
        ConversationRepository conversations = mock(ConversationRepository.class);
        MessageRepository messages = mock(MessageRepository.class);
        ChatStreamPersistenceService service = new ChatStreamPersistenceService(
                conversations, messages, new ObjectMapper());
        ChatStreamPersistenceService.StreamCapture capture = service.capture();

        capture.accept(event("reasoning_start", Map.of(
                "requestedThinkingMode", "deep",
                "effectiveThinkingMode", "deep",
                "effectiveReasoningEffort", "max"
        )));
        capture.accept(event("reasoning_delta", Map.of("delta", "raw private reasoning")));
        capture.accept(event("reasoning_end", Map.of("reasoningPhaseMs", 1200)));
        capture.accept(event("content_delta", Map.of("delta", "final ")));
        capture.accept(event("content_delta", Map.of("delta", "answer")));
        capture.accept(event("usage", Map.of(
                "reasoning_tokens", 320,
                "total_tokens", 500,
                "effectiveModel", "deepseek-v4-pro"
        )));
        capture.accept(event("done", Map.of("status", "completed")));

        ChatStreamPersistenceService.PreparedStream prepared =
                new ChatStreamPersistenceService.PreparedStream(UUID.randomUUID(), "ctx-test", Map.of());
        service.complete(prepared, capture);

        var captor = org.mockito.ArgumentCaptor.forClass(Message.class);
        verify(messages).save(captor.capture());
        Message saved = captor.getValue();
        assertEquals("final answer", saved.getContent());
        assertEquals(320, saved.getMetadata().get("reasoningTokens"));
        assertEquals(500, saved.getMetadata().get("totalTokens"));
        assertTrue((Boolean) saved.getMetadata().get("thinkingEnabled"));
        assertFalse(saved.getMetadata().toString().contains("raw private reasoning"));
        assertFalse(saved.getMetadata().containsKey("reasoning_content"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void persistsSanitizedToolExecutionsAndSources() {
        ConversationRepository conversations = mock(ConversationRepository.class);
        MessageRepository messages = mock(MessageRepository.class);
        ChatStreamPersistenceService service = new ChatStreamPersistenceService(
                conversations, messages, new ObjectMapper());
        ChatStreamPersistenceService.StreamCapture capture = service.capture();

        capture.accept(event("tool_result", Map.of(
                "callId", "call-1",
                "toolName", "web_search",
                "status", "completed",
                "durationMs", 12,
                "outputSummary", "Found one result.",
                "sourceRefs", List.of("src-1"),
                "sources", List.of(Map.of(
                        "citationId", "src-1",
                        "title", "Public source",
                        "url", "https://example.test/source",
                        "snippet", "Short public snippet.",
                        "provider", "test",
                        "retrievedAt", "2026-01-01T00:00:00Z",
                        "content", "full page body must not be persisted"
                ))
        )));
        capture.accept(event("content_delta", Map.of("delta", "cited answer")));
        capture.accept(event("done", Map.of(
                "status", "completed",
                "toolsUsed", List.of("web_search")
        )));

        ChatStreamPersistenceService.PreparedStream prepared =
                new ChatStreamPersistenceService.PreparedStream(UUID.randomUUID(), "ctx-tools", Map.of());
        service.complete(prepared, capture);

        var captor = org.mockito.ArgumentCaptor.forClass(Message.class);
        verify(messages).save(captor.capture());
        Map<String, Object> metadata = captor.getValue().getMetadata();
        List<Map<String, Object>> executions =
                (List<Map<String, Object>>) metadata.get("toolExecutions");
        List<Map<String, Object>> sources =
                (List<Map<String, Object>>) metadata.get("sources");

        assertEquals("web_search", executions.get(0).get("toolName"));
        assertEquals(12, executions.get(0).get("durationMs"));
        assertEquals("https://example.test/source", sources.get(0).get("url"));
        assertFalse(sources.get(0).containsKey("content"));
        assertTrue(metadata.toString().contains("tool:web_search"));
        assertFalse(metadata.toString().contains("full page body"));
    }

    private ServerSentEvent<String> event(String type, Map<String, Object> data) {
        try {
            String json = new ObjectMapper().writeValueAsString(Map.of(
                    "event", type,
                    "requestId", "request-1",
                    "sequence", 1,
                    "data", data
            ));
            return ServerSentEvent.builder(json).event(type).build();
        } catch (Exception error) {
            throw new AssertionError(error);
        }
    }
}
