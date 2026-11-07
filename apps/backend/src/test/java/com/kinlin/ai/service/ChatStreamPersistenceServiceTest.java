package com.kinlin.ai.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.http.codec.ServerSentEvent;

import java.util.Map;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.any;

class ChatStreamPersistenceServiceTest {

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    @SuppressWarnings("unchecked")
    void modelHistoryExcludesOnlyTheSavedCurrentMessageAndKeepsRepeatedPriorText() {
        UUID userId = UUID.randomUUID(), conversationId = UUID.randomUUID();
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(userId, null, List.of()));
        var conversations = mock(ConversationRepository.class);
        var messages = mock(MessageRepository.class);
        var conversation = new Conversation();
        conversation.setId(conversationId); conversation.setContextId("ctx-compact");
        conversation.setUserId(userId); conversation.setWorkspaceMode("chat");
        when(conversations.findByContextId("ctx-compact")).thenReturn(Optional.of(conversation));
        Message earlier = new Message(); earlier.setId(UUID.randomUUID());
        earlier.setRole(Message.MessageRole.USER); earlier.setContent("continue");
        Message answer = new Message(); answer.setId(UUID.randomUUID());
        answer.setRole(Message.MessageRole.ASSISTANT); answer.setContent("previous answer");
        java.util.ArrayList<Message> database = new java.util.ArrayList<>(List.of(earlier, answer));
        when(messages.save(any(Message.class))).thenAnswer(invocation -> {
            Message saved = invocation.getArgument(0); saved.setId(UUID.randomUUID()); database.add(saved); return saved;
        });
        when(messages.findByConversationIdOrderByCreatedAtAsc(conversationId)).thenAnswer(invocation -> database);
        var prepared = new ChatStreamPersistenceService(conversations, messages, new ObjectMapper())
                .prepare(Map.of("text", "continue", "context_id", "ctx-compact"));
        var context = (List<Map<String, String>>) prepared.body().get("context");
        assertEquals(List.of(Map.of("role", "user", "content", "continue"),
                             Map.of("role", "assistant", "content", "previous answer")), context);
        assertEquals(3, database.size()); // Original persistence still stores this request once.
        assertEquals("continue", prepared.body().get("text")); // Python alone appends this turn.
    }

    @Test
    void doesNotReuseAStreamConversationFromAnotherWorkspace() {
        UUID userId = UUID.randomUUID();
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(userId, null, List.of()));
        ConversationRepository conversations = mock(ConversationRepository.class);
        MessageRepository messages = mock(MessageRepository.class);
        ChatStreamPersistenceService service = new ChatStreamPersistenceService(
                conversations, messages, new ObjectMapper());

        Conversation existing = new Conversation();
        existing.setId(UUID.randomUUID());
        existing.setContextId("ctx-chat");
        existing.setWorkspaceMode("chat");
        when(conversations.findByContextId("ctx-chat")).thenReturn(Optional.of(existing));
        when(conversations.save(any(Conversation.class))).thenAnswer(invocation -> {
            Conversation saved = invocation.getArgument(0);
            saved.setId(UUID.randomUUID());
            return saved;
        });

        ChatStreamPersistenceService.PreparedStream prepared = service.prepare(Map.of(
                "text", "agent task",
                "context_id", "ctx-chat",
                "workspace_mode", "agent"
        ));

        var captor = org.mockito.ArgumentCaptor.forClass(Conversation.class);
        verify(conversations).save(captor.capture());
        assertEquals("agent", captor.getValue().getWorkspaceMode());
        assertFalse("ctx-chat".equals(captor.getValue().getContextId()));
        assertEquals(captor.getValue().getContextId(), prepared.contextId());
        assertEquals("agent", prepared.body().get("workspace_mode"));
    }

    @Test
    void doesNotReuseAStreamConversationOwnedByAnotherUser() {
        UUID userId = UUID.randomUUID();
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(userId, null, List.of()));
        ConversationRepository conversations = mock(ConversationRepository.class);
        MessageRepository messages = mock(MessageRepository.class);
        ChatStreamPersistenceService service = new ChatStreamPersistenceService(
                conversations, messages, new ObjectMapper());

        Conversation existing = new Conversation();
        existing.setId(UUID.randomUUID());
        existing.setContextId("ctx-other-user");
        existing.setUserId(UUID.randomUUID());
        existing.setWorkspaceMode("chat");
        when(conversations.findByContextId("ctx-other-user")).thenReturn(Optional.of(existing));
        when(conversations.save(any(Conversation.class))).thenAnswer(invocation -> {
            Conversation saved = invocation.getArgument(0);
            saved.setId(UUID.randomUUID());
            return saved;
        });

        ChatStreamPersistenceService.PreparedStream prepared = service.prepare(Map.of(
                "text", "private task",
                "context_id", "ctx-other-user",
                "workspace_mode", "chat"
        ));

        var captor = org.mockito.ArgumentCaptor.forClass(Conversation.class);
        verify(conversations).save(captor.capture());
        assertEquals(userId, captor.getValue().getUserId());
        assertFalse("ctx-other-user".equals(prepared.contextId()));
    }

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

    @Test
    @SuppressWarnings("unchecked")
    void persistsRunCommandSummaryWithCallIdAndTerminalForHistoryRestore() {
        MessageRepository messages = mock(MessageRepository.class);
        ChatStreamPersistenceService service = new ChatStreamPersistenceService(
                mock(ConversationRepository.class), messages, new ObjectMapper());
        ChatStreamPersistenceService.StreamCapture capture = service.capture();

        Map<String, Object> terminal = Map.of(
                "command", "echo RUN_OK",
                "cwd", ".",
                "exitCode", 0,
                "stdout", "RUN_OK\n",
                "stderr", "",
                "timedOut", false,
                "truncated", false
        );
        capture.accept(event("tool_result", Map.of(
                "callId", "call-9",
                "toolName", "run_command",
                "status", "completed",
                "durationMs", 88,
                "outputSummary", "Command completed (exit code 0)",
                "terminal", terminal
        )));
        capture.accept(event("done", Map.of("status", "completed")));

        ChatStreamPersistenceService.PreparedStream prepared =
                new ChatStreamPersistenceService.PreparedStream(UUID.randomUUID(), "ctx-run-cmd", Map.of());
        service.complete(prepared, capture);

        var captor = org.mockito.ArgumentCaptor.forClass(Message.class);
        verify(messages).save(captor.capture());
        Map<String, Object> metadata = captor.getValue().getMetadata();
        List<Map<String, Object>> summary =
                (List<Map<String, Object>>) metadata.get("executionSummary");

        Map<String, Object> stage = summary.stream()
                .filter(item -> String.valueOf(item.get("stage")).startsWith("tool:run_command"))
                .findFirst()
                .orElseThrow();
        // stage 带 callId（与流式期间一致，刷新恢复后同一键）；terminal 完整回传供侧栏还原
        assertEquals("tool:run_command:call-9", stage.get("stage"));
        assertEquals("completed", stage.get("status"));
        assertEquals(88, stage.get("durationMs"));
        assertEquals(terminal, stage.get("terminal"));
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

    @Test
    void persistsFailedPartialReplyOnceWithoutRawReasoningOrErrorPayload() {
        MessageRepository messages = mock(MessageRepository.class);
        ChatStreamPersistenceService service = new ChatStreamPersistenceService(
                mock(ConversationRepository.class), messages, new ObjectMapper());
        var capture = service.capture();
        capture.accept(event("reasoning_delta", Map.of("delta", "private reasoning")));
        capture.accept(event("content_delta", Map.of("delta", "partial answer")));
        capture.accept(ServerSentEvent.builder("{\"code\":\"AUTH_SESSION_INVALIDATED\"}")
                .event("auth.invalidated").build());
        var prepared = new ChatStreamPersistenceService.PreparedStream(UUID.randomUUID(), "ctx", Map.of("model", "deepseek-flash"));
        service.complete(prepared, capture);
        service.complete(prepared, capture);
        var captor = org.mockito.ArgumentCaptor.forClass(Message.class);
        verify(messages).save(captor.capture());
        assertEquals("partial answer", captor.getValue().getContent());
        assertTrue(captor.getValue().getMetadata().toString().contains("登录会话"));
        assertTrue(captor.getValue().getMetadata().toString().contains("failed"));
        assertFalse(captor.getValue().getMetadata().toString().contains("private reasoning"));
        assertEquals("deepseek-flash", captor.getValue().getMetadata().get("model_info"));
    }

    @Test
    void persistsCancellationWithoutInventingModelContent() {
        MessageRepository messages = mock(MessageRepository.class);
        ChatStreamPersistenceService service = new ChatStreamPersistenceService(
                mock(ConversationRepository.class), messages, new ObjectMapper());
        var capture = service.capture();
        capture.cancel();
        service.complete(new ChatStreamPersistenceService.PreparedStream(UUID.randomUUID(), "ctx", Map.of()), capture);
        var captor = org.mockito.ArgumentCaptor.forClass(Message.class);
        verify(messages).save(captor.capture());
        assertEquals("已停止生成", captor.getValue().getContent());
        assertTrue(captor.getValue().getMetadata().toString().contains("cancelled"));
    }

    @Test
    void retryContextExcludesFailedRepliesAndKeepsSuccessfulContent() {
        UUID userId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(userId, null, List.of()));
        Conversation conversation = new Conversation();
        conversation.setId(conversationId);
        conversation.setUserId(userId);
        conversation.setContextId("ctx-retry");
        conversation.setWorkspaceMode("chat");
        ConversationRepository conversations = mock(ConversationRepository.class);
        when(conversations.findByContextId("ctx-retry")).thenReturn(Optional.of(conversation));
        MessageRepository messages = mock(MessageRepository.class);
        Message failed = new Message();
        failed.setRole(Message.MessageRole.ASSISTANT);
        failed.setContent("failure text must not become model input");
        failed.setMetadata(Map.of("executionSummary", List.of(Map.of("stage", "chat_stream", "status", "failed"))));
        Message successful = new Message();
        successful.setRole(Message.MessageRole.ASSISTANT);
        successful.setContent("previous answer");
        when(messages.findByConversationIdOrderByCreatedAtAsc(conversationId)).thenReturn(List.of(failed, successful));
        var prepared = new ChatStreamPersistenceService(conversations, messages, new ObjectMapper())
                .prepare(Map.of("context_id", "ctx-retry", "text", "try again"));
        assertEquals(List.of(Map.of("role", "assistant", "content", "previous answer")), prepared.body().get("context"));
    }
}
