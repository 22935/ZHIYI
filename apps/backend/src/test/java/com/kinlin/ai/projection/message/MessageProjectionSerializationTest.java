package com.kinlin.ai.projection.message;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.projection.message.dto.MessageMetadataQuery;
import com.kinlin.ai.projection.message.dto.MessageQuery;
import com.kinlin.ai.projection.message.mapper.MessageProjectionMapper;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

/** Whitelist, wire-name and time-format checks for the message query projection. */
class MessageProjectionSerializationTest {

    private static final String LONG_CONTENT = "长".repeat(2000);

    /** Mirrors JacksonConfig: JavaTimeModule + ISO strings. */
    private final ObjectMapper jackson = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    @Test
    void metadataKeepsOnlyTheWhitelistedPublicKeysWithLegacyWireNames() throws Exception {
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("confidence", 0.87);
        metadata.put("tokens_used", 410);
        metadata.put("totalTokens", 1320L);
        metadata.put("effectiveModel", "glm-4.7");
        metadata.put("model_info", "legacy-model");
        metadata.put("requestedThinkingMode", "enabled");
        metadata.put("effectiveThinkingMode", "enabled");
        metadata.put("effectiveReasoningEffort", "high");
        metadata.put("reasoningPhaseMs", 812);
        metadata.put("inputTokens", 900);
        metadata.put("reasoningTokens", 220);
        metadata.put("outputTokens", 200);
        metadata.put("latencyMs", 1730);
        metadata.put("thinkingEnabled", true);
        metadata.put("reasoningContent", "bounded reasoning");
        metadata.put("reasoningTruncated", true);
        metadata.put("executionSummary", List.of(Map.of(
                "stage", "tool:web_search",
                "status", "completed",
                "description", "web_search 调用完成")));
        // internal producers that must not surface in the public response
        metadata.put("role_context", Map.of("system_prompt", "SECRET-PROMPT"));
        metadata.put("sources", List.of(Map.of("url", "https://secret.internal/x")));
        metadata.put("reasoning_path", List.of(Map.of("title", "SECRET-REASONING")));
        metadata.put("agent_mode", "planner");
        metadata.put("toolExecutions", List.of(Map.of("callId", "call_1", "inputSummary", "SECRET-INPUT")));
        metadata.put("toolsUsed", List.of("web_search"));
        metadata.put("fallbackUsed", false);
        metadata.put("resolutionReasons", List.of("cache"));

        Message message = message(Message.MessageRole.ASSISTANT, metadata);
        String encoded = jackson.writeValueAsString(MessageProjectionMapper.toQuery(message));
        JsonNode json = jackson.readTree(encoded).get("metadata");

        assertEquals(0.87, json.get("confidence").asDouble());
        assertEquals(410, json.get("tokens_used").asLong());
        assertEquals(1320, json.get("totalTokens").asLong());
        assertEquals("glm-4.7", json.get("effectiveModel").asText());
        assertEquals("legacy-model", json.get("model_info").asText());
        assertEquals("enabled", json.get("requestedThinkingMode").asText());
        assertEquals("enabled", json.get("effectiveThinkingMode").asText());
        assertEquals("high", json.get("effectiveReasoningEffort").asText());
        assertEquals(812, json.get("reasoningPhaseMs").asLong());
        assertEquals(900, json.get("inputTokens").asLong());
        assertEquals(220, json.get("reasoningTokens").asLong());
        assertEquals(200, json.get("outputTokens").asLong());
        assertEquals(1730, json.get("latencyMs").asLong());
        assertTrue(json.get("thinkingEnabled").asBoolean());
        assertEquals("bounded reasoning", json.get("reasoningContent").asText());
        assertTrue(json.get("reasoningTruncated").asBoolean());
        assertEquals("tool:web_search", json.get("executionSummary").get(0).get("stage").asText());
        assertEquals("completed", json.get("executionSummary").get(0).get("status").asText());
        assertEquals("web_search 调用完成", json.get("executionSummary").get(0).get("description").asText());

        assertEquals(17, json.size(), "metadata key set must stay the closed whitelist");
        for (String forbidden : List.of("role_context", "sources", "reasoning_path", "agent_mode",
                "toolExecutions", "toolsUsed", "fallbackUsed", "resolutionReasons")) {
            assertFalse(json.has(forbidden), forbidden + " must not be exposed");
        }
        assertFalse(encoded.contains("SECRET"));
    }

    @Test
    void messageBodyKeepsEntityFieldNamesEnumsTimesAndFullContent() throws Exception {
        Message message = message(Message.MessageRole.USER, null);
        message.setContent(LONG_CONTENT);
        message.setFileUrl("/files/download/chat/a.png");
        message.setMessageType(Message.MessageType.IMAGE);
        JsonNode json = jackson.readTree(jackson.writeValueAsString(MessageProjectionMapper.toQuery(message)));
        assertEquals(8, json.size(), "field set must stay the closed whitelist");
        assertEquals("USER", json.get("role").asText());
        assertEquals("IMAGE", json.get("messageType").asText());
        assertEquals("/files/download/chat/a.png", json.get("fileUrl").asText());
        assertEquals("2026-09-30T08:30:15", json.get("createdAt").asText());
        assertEquals(LONG_CONTENT.length(), json.get("content").asText().length(), "正文不截断");
        assertTrue(json.get("metadata").isNull());
        assertTrue(json.get("id").asText().matches("^[0-9a-f-]{36}$"));
    }

    @Test
    void absentMetadataAndTypeMismatchesNeverFabricateValues() throws Exception {
        Message plain = message(Message.MessageRole.USER, null);
        assertNull(MessageProjectionMapper.toQuery(plain).metadata());
        assertNull(MessageProjectionMapper.toQuery(message(Message.MessageRole.USER, Map.of())).metadata());

        Map<String, Object> mismatched = new HashMap<>();
        mismatched.put("inputTokens", "not-a-number");
        mismatched.put("confidence", "high");
        mismatched.put("thinkingEnabled", "yes");
        mismatched.put("effectiveModel", 42);
        mismatched.put("latencyMs", 1.5);
        mismatched.put("executionSummary", "not-a-list");
        MessageQuery query = MessageProjectionMapper.toQuery(message(Message.MessageRole.ASSISTANT, mismatched));
        assertNull(query.metadata().inputTokens());
        assertNull(query.metadata().confidence());
        assertNull(query.metadata().thinkingEnabled());
        assertNull(query.metadata().effectiveModel());
        assertNull(query.metadata().latencyMs());
        assertNull(query.metadata().executionSummary());

        Map<String, Object> partial = new HashMap<>();
        partial.put("executionSummary", List.of(
                Map.of("stage", "reasoning", "status", "completed", "description", "模型完成思考阶段"),
                Map.of("stage", "broken", "status", 7, "description", "类型不符")));
        MessageQuery withStages = MessageProjectionMapper.toQuery(message(
                Message.MessageRole.ASSISTANT, partial));
        assertEquals(1, withStages.metadata().executionSummary().size());
        assertEquals("reasoning", withStages.metadata().executionSummary().get(0).stage());
    }

    @Test
    void numericReadsAreExactAndNeverFabricateObservations() throws Exception {
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("totalTokens", new java.math.BigInteger("9223372036854775808")); // 2^63：旧实现回绕成负数
        metadata.put("inputTokens", new java.math.BigInteger("9223372036854775807")); // Long.MAX_VALUE：精确保留
        metadata.put("outputTokens", new java.math.BigDecimal("12.5"));               // 小数计数：不截断成 12
        metadata.put("reasoningTokens", new java.math.BigDecimal("900"));             // 整数十进制：精确
        metadata.put("latencyMs", 1200.0);                                            // 数学整数的 double：精确
        metadata.put("reasoningPhaseMs", 1200.5);                                     // 小数 double：省略
        metadata.put("tokens_used", 1e20);                                            // 整数但越界 long：省略
        MessageMetadataQuery query = MessageProjectionMapper.toQuery(
                message(Message.MessageRole.ASSISTANT, metadata)).metadata();
        assertNull(query.totalTokens(), "2^63 不得回绕成 -9223372036854775808");
        assertEquals(Long.MAX_VALUE, query.inputTokens());
        assertNull(query.outputTokens(), "12.5 不得截断成 12");
        assertEquals(900L, query.reasoningTokens());
        assertEquals(1200L, query.latencyMs());
        assertNull(query.reasoningPhaseMs());
        assertNull(query.tokensUsed(), "越界整型 double 不得钳制到 Long.MAX_VALUE");

        for (Number invalid : List.of(Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY,
                Double.NaN, Float.NaN, new java.math.BigDecimal("1e999"))) {
            MessageQuery nonFinite = MessageProjectionMapper.toQuery(message(
                    Message.MessageRole.ASSISTANT, Map.of("confidence", invalid)));
            assertNull(nonFinite.metadata().confidence());
            String actual = jackson.writeValueAsString(nonFinite);
            assertTrue(jackson.readTree(actual).get("metadata").get("confidence").isNull());
            assertFalse(actual.contains("Infinity") || actual.contains("NaN"),
                    "the actual non-finite input must not escape through serialization");
        }

        String encoded = jackson.writeValueAsString(MessageProjectionMapper.toQuery(message(
                Message.MessageRole.ASSISTANT, metadata)));
        assertFalse(encoded.contains("-9223372036854775808"), "不得出现回绕值");
    }

    @Test
    void floatingCountsRespectTheExclusiveUpperBoundAndExactLowerBound() throws Exception {
        for (Number invalid : List.of(0x1p63, 0x1p63f, (double) Long.MAX_VALUE,
                Math.nextDown(-0x1p63), Double.POSITIVE_INFINITY, Double.NaN)) {
            MessageQuery query = MessageProjectionMapper.toQuery(message(
                    Message.MessageRole.ASSISTANT, Map.of("totalTokens", invalid)));
            assertNull(query.metadata().totalTokens(), invalid + " must not clamp or wrap");
            assertTrue(jackson.readTree(jackson.writeValueAsString(query))
                    .get("metadata").get("totalTokens").isNull());
        }
        for (Number minimum : List.of(-0x1p63, -0x1p63f)) {
            MessageQuery query = MessageProjectionMapper.toQuery(message(
                    Message.MessageRole.ASSISTANT, Map.of("totalTokens", minimum)));
            assertEquals(Long.MIN_VALUE, query.metadata().totalTokens());
            assertEquals(Long.MIN_VALUE, jackson.readTree(jackson.writeValueAsString(query))
                    .get("metadata").get("totalTokens").longValue());
        }
        MessageQuery belowMaximum = MessageProjectionMapper.toQuery(message(
                Message.MessageRole.ASSISTANT, Map.of("totalTokens", Math.nextDown(0x1p63))));
        assertEquals(9223372036854774784L, belowMaximum.metadata().totalTokens());
        assertEquals(9223372036854774784L, jackson.readTree(jackson.writeValueAsString(belowMaximum))
                .get("metadata").get("totalTokens").longValue());
    }

    @Test
    void listProjectionPreservesOrderAndNullRoleHandling() {
        Message first = message(Message.MessageRole.USER, null);
        Message second = message(Message.MessageRole.ASSISTANT, null);
        List<MessageQuery> projected = MessageProjectionMapper.toQuery(List.of(first, second));
        assertEquals(2, projected.size());
        assertEquals(projected.get(0).id(), first.getId());
        assertEquals(projected.get(1).id(), second.getId());
    }

    private Message message(Message.MessageRole role, Map<String, Object> metadata) {
        Message message = new Message();
        message.setId(UUID.randomUUID());
        message.setConversationId(UUID.randomUUID());
        message.setRole(role);
        message.setContent("正文");
        message.setMessageType(Message.MessageType.TEXT);
        message.setMetadata(metadata);
        message.setCreatedAt(LocalDateTime.of(2026, 9, 30, 8, 30, 15));
        return message;
    }
}
