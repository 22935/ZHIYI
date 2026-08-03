package com.kinlin.ai.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import com.kinlin.ai.security.AuthenticatedUser;
import lombok.RequiredArgsConstructor;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Persists stream results while explicitly excluding raw reasoning deltas. */
@Service
@RequiredArgsConstructor
public class ChatStreamPersistenceService {

    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;
    private final ObjectMapper objectMapper;

    @Transactional
    public PreparedStream prepare(Map<String, Object> requestBody) {
        UUID userId = AuthenticatedUser.currentUserId()
                .orElseThrow(() -> new IllegalStateException("Authenticated user is required for chat streaming"));
        Map<String, Object> body = new LinkedHashMap<>(requestBody == null ? Map.of() : requestBody);
        String text = stringValue(body.get("text"));
        String contextId = stringValue(body.get("context_id"));
        String workspaceMode = normalizeWorkspaceMode(body.get("workspace_mode"));
        UUID roleId = uuidValue(body.get("role_id"));

        Conversation conversation = contextId.isBlank()
                ? createConversation(userId, roleId, text, workspaceMode)
                : conversationRepository.findByContextId(contextId)
                        .filter(item -> workspaceMode.equals(item.getWorkspaceMode()))
                        .orElseGet(() -> createConversation(userId, roleId, text, workspaceMode));

        Message userMessage = new Message();
        userMessage.setConversationId(conversation.getId());
        userMessage.setRole(Message.MessageRole.USER);
        userMessage.setContent(text);
        userMessage.setMessageType(Message.MessageType.TEXT);
        messageRepository.save(userMessage);

        body.put("context_id", conversation.getContextId());
        if (!(body.get("context") instanceof List<?>)) {
            body.put("context", buildContext(conversation.getId()));
        }
        return new PreparedStream(conversation.getId(), conversation.getContextId(), body);
    }

    public StreamCapture capture() {
        return new StreamCapture(objectMapper);
    }

    @Transactional
    public void complete(PreparedStream prepared, StreamCapture capture) {
        if (!capture.completed || capture.content.isEmpty()) {
            return;
        }
        Message assistantMessage = new Message();
        assistantMessage.setConversationId(prepared.conversationId());
        assistantMessage.setRole(Message.MessageRole.ASSISTANT);
        assistantMessage.setContent(capture.content.toString());
        assistantMessage.setMessageType(Message.MessageType.TEXT);
        assistantMessage.setMetadata(capture.metadata());
        messageRepository.save(assistantMessage);
    }

    private Conversation createConversation(UUID userId, UUID roleId, String text, String workspaceMode) {
        return createConversation(userId, roleId, text, "ctx_" + UUID.randomUUID(), workspaceMode);
    }

    private Conversation createConversation(UUID userId, UUID roleId, String text, String contextId, String workspaceMode) {
        Conversation conversation = new Conversation();
        conversation.setUserId(userId);
        conversation.setRoleId(roleId);
        conversation.setContextId(contextId);
        conversation.setTitle(text.length() > 50 ? text.substring(0, 50) + "..." : text);
        conversation.setWorkspaceMode(workspaceMode);
        return conversationRepository.save(conversation);
    }

    private String normalizeWorkspaceMode(Object value) {
        return "agent".equalsIgnoreCase(stringValue(value)) ? "agent" : "chat";
    }

    private List<Map<String, String>> buildContext(UUID conversationId) {
        return messageRepository.findByConversationIdOrderByCreatedAtAsc(conversationId).stream()
                .filter(message -> message.getContent() != null && !message.getContent().isBlank())
                .map(message -> Map.of(
                        "role", message.getRole() == Message.MessageRole.USER ? "user" : "assistant",
                        "content", message.getContent()
                ))
                .toList();
    }

    private String stringValue(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private UUID uuidValue(Object value) {
        try {
            String text = stringValue(value);
            return text.isBlank() ? null : UUID.fromString(text);
        } catch (IllegalArgumentException ignored) {
            return null;
        }
    }

    public record PreparedStream(UUID conversationId, String contextId, Map<String, Object> body) { }

    public static final class StreamCapture {
        private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() { };
        private final ObjectMapper objectMapper;
        private final StringBuilder content = new StringBuilder();
        private final Map<String, Object> usage = new LinkedHashMap<>();
        private final List<Map<String, Object>> toolExecutions = new ArrayList<>();
        private final Map<String, Map<String, Object>> sources = new LinkedHashMap<>();
        private boolean reasoningStarted;
        private boolean reasoningCompleted;
        private boolean contentStarted;
        private boolean completed;

        private StreamCapture(ObjectMapper objectMapper) {
            this.objectMapper = objectMapper;
        }

        @SuppressWarnings("unchecked")
        public void accept(ServerSentEvent<String> event) {
            if (event == null || event.data() == null || event.data().isBlank()) {
                return;
            }
            try {
                Map<String, Object> envelope = objectMapper.readValue(event.data(), MAP_TYPE);
                String type = String.valueOf(envelope.getOrDefault("event", event.event()));
                Object rawData = envelope.get("data");
                Map<String, Object> data = rawData instanceof Map<?, ?>
                        ? (Map<String, Object>) rawData
                        : Map.of();
                switch (type) {
                    case "reasoning_start" -> {
                        reasoningStarted = true;
                        copy(data, "requestedThinkingMode", "effectiveThinkingMode", "effectiveReasoningEffort");
                    }
                    case "reasoning_end" -> {
                        reasoningCompleted = true;
                        copy(data, "reasoningPhaseMs");
                    }
                    case "content_delta" -> {
                        Object delta = data.get("delta");
                        if (delta != null) {
                            contentStarted = true;
                            content.append(delta);
                        }
                    }
                    case "tool_result", "tool_error" -> {
                        addToolExecution(data);
                        addSources(data.get("sources"));
                    }
                    case "usage" -> copy(data,
                            "inputTokens", "input_tokens",
                            "reasoningTokens", "reasoning_tokens",
                            "outputTokens", "output_tokens",
                            "totalTokens", "total_tokens",
                            "latencyMs", "requestedModel", "effectiveModel",
                            "requestedThinkingMode", "effectiveThinkingMode",
                            "effectiveReasoningEffort", "resolutionReasons");
                    case "done" -> {
                        completed = "completed".equals(String.valueOf(data.get("status")));
                        addSources(data.get("sources"));
                        Object records = data.get("toolExecutions");
                        if (toolExecutions.isEmpty() && records instanceof List<?> items) {
                            for (Object item : items) {
                                if (item instanceof Map<?, ?> map) {
                                    addToolExecution((Map<String, Object>) map);
                                }
                            }
                        }
                        copy(data, "toolsUsed");
                    }
                    default -> {
                        // reasoning_delta and error are intentionally not persisted as message metadata.
                    }
                }
            } catch (Exception ignored) {
                // Malformed stream events remain visible to the client but never enter persistence.
            }
        }

        public Map<String, Object> metadata() {
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.putAll(usage);
            normalizeTokenName(metadata, "input_tokens", "inputTokens");
            normalizeTokenName(metadata, "reasoning_tokens", "reasoningTokens");
            normalizeTokenName(metadata, "output_tokens", "outputTokens");
            normalizeTokenName(metadata, "total_tokens", "totalTokens");
            metadata.put("thinkingEnabled", reasoningStarted);
            metadata.putIfAbsent("fallbackUsed", false);
            if (!toolExecutions.isEmpty()) {
                metadata.put("toolExecutions", List.copyOf(toolExecutions));
                metadata.putIfAbsent("toolsUsed", toolExecutions.stream()
                        .map(item -> String.valueOf(item.getOrDefault("toolName", "unknown")))
                        .distinct()
                        .toList());
            }
            if (!sources.isEmpty()) {
                metadata.put("sources", List.copyOf(sources.values()));
            }
            List<Map<String, String>> summary = new ArrayList<>();
            for (Map<String, Object> item : toolExecutions) {
                String toolName = String.valueOf(item.getOrDefault("toolName", "unknown"));
                String status = String.valueOf(item.getOrDefault("status", "completed"));
                summary.add(Map.of(
                        "stage", "tool:" + toolName,
                        "status", status,
                        "description", "failed".equals(status)
                                ? toolName + " 调用失败"
                                : toolName + " 调用完成"
                ));
            }
            if (reasoningStarted) {
                summary.add(Map.of(
                        "stage", "reasoning",
                        "status", reasoningCompleted ? "completed" : "interrupted",
                        "description", reasoningCompleted ? "模型完成思考阶段" : "模型思考阶段未完整结束"
                ));
            }
            if (contentStarted) {
                summary.add(Map.of(
                        "stage", "answer_generation",
                        "status", completed ? "completed" : "interrupted",
                        "description", completed ? "模型完成最终回答生成" : "最终回答生成未完整结束"
                ));
            }
            metadata.put("executionSummary", summary);
            return metadata;
        }

        private void copy(Map<String, Object> data, String... keys) {
            for (String key : keys) {
                if (data.containsKey(key) && data.get(key) != null) {
                    usage.put(key, data.get(key));
                }
            }
        }

        private void normalizeTokenName(Map<String, Object> metadata, String oldName, String newName) {
            if (!metadata.containsKey(newName) && metadata.containsKey(oldName)) {
                metadata.put(newName, metadata.remove(oldName));
            } else {
                metadata.remove(oldName);
            }
        }

        private void addToolExecution(Map<String, Object> data) {
            String callId = String.valueOf(data.getOrDefault("callId", ""));
            if (!callId.isBlank() && toolExecutions.stream()
                    .anyMatch(item -> callId.equals(String.valueOf(item.get("callId"))))) {
                return;
            }
            Map<String, Object> record = new LinkedHashMap<>();
            for (String key : List.of(
                    "callId", "toolName", "status", "durationMs", "inputSummary",
                    "outputSummary", "sourceRefs", "errorCode"
            )) {
                if (data.containsKey(key) && data.get(key) != null) {
                    record.put(key, data.get(key));
                }
            }
            if (!record.isEmpty()) {
                toolExecutions.add(record);
            }
        }

        @SuppressWarnings("unchecked")
        private void addSources(Object value) {
            if (!(value instanceof List<?> items)) {
                return;
            }
            for (Object item : items) {
                if (!(item instanceof Map<?, ?> raw)) {
                    continue;
                }
                Map<String, Object> source = new LinkedHashMap<>();
                for (String key : List.of(
                        "citationId", "title", "filename", "url", "snippet", "provider", "retrievedAt"
                )) {
                    if (raw.containsKey(key) && raw.get(key) != null) {
                        source.put(key, raw.get(key));
                    }
                }
                String key = String.valueOf(source.getOrDefault(
                        "citationId", source.getOrDefault("url", source.getOrDefault("title", ""))
                ));
                if (!key.isBlank()) {
                    sources.putIfAbsent(key, source);
                }
            }
        }
    }
}
