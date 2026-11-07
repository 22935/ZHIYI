package com.kinlin.ai.projection.message.mapper;

import com.kinlin.ai.entity.Message;
import com.kinlin.ai.projection.message.dto.MessageMetadataQuery;
import com.kinlin.ai.projection.message.dto.MessageQuery;
import com.kinlin.ai.projection.message.dto.MessageRoleQuery;
import com.kinlin.ai.projection.message.dto.MessageTypeQuery;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Pure output adapter over persisted messages; no service, repository, transport or
 * cache calls. Metadata keeps only the whitelisted public keys; optional fields whose
 * persisted value has an unexpected JSON type are omitted (null) instead of coerced.
 * Numeric reads are exact: fractional counts, out-of-range integers and non-finite
 * values never become fabricated observations (no silent wrap-around or truncation).
 */
public final class MessageProjectionMapper {
    private MessageProjectionMapper() { }

    public static MessageQuery toQuery(Message message) {
        return new MessageQuery(message.getId(), message.getConversationId(),
                message.getRole() == null ? null : MessageRoleQuery.valueOf(message.getRole().name()),
                message.getContent(),
                message.getMessageType() == null ? null : MessageTypeQuery.valueOf(message.getMessageType().name()),
                message.getFileUrl(),
                metadata(message.getMetadata()),
                message.getCreatedAt());
    }

    public static List<MessageQuery> toQuery(List<Message> messages) {
        List<MessageQuery> projected = new ArrayList<>(messages.size());
        for (Message message : messages) {
            projected.add(toQuery(message));
        }
        return projected;
    }

    private static MessageMetadataQuery metadata(Map<String, Object> source) {
        if (source == null || source.isEmpty()) {
            return null;
        }
        return new MessageMetadataQuery(
                decimal(source.get("confidence")),
                whole(source.get("tokens_used")),
                whole(source.get("totalTokens")),
                text(source.get("effectiveModel")),
                text(source.get("model_info")),
                text(source.get("requestedThinkingMode")),
                text(source.get("effectiveThinkingMode")),
                text(source.get("effectiveReasoningEffort")),
                whole(source.get("reasoningPhaseMs")),
                whole(source.get("inputTokens")),
                whole(source.get("reasoningTokens")),
                whole(source.get("outputTokens")),
                whole(source.get("latencyMs")),
                flag(source.get("thinkingEnabled")),
                text(source.get("reasoningContent")),
                flag(source.get("reasoningTruncated")),
                stages(source.get("executionSummary")));
    }

    /** Finite doubles only; NaN/Infinity would leave the JSON number space. */
    private static Double decimal(Object value) {
        if (!(value instanceof Number number)) {
            return null;
        }
        double converted = number.doubleValue();
        return Double.isFinite(converted) ? converted : null;
    }

    /**
     * Exact integral mapping only: fixed-width integers pass through, BigInteger/BigDecimal
     * via {@code longValueExact} (fraction or overflow drops to null), floats/doubles only
     * when finite, mathematically integral and inside the long range.
     */
    private static Long whole(Object value) {
        if (value instanceof Byte || value instanceof Short || value instanceof Integer || value instanceof Long) {
            return ((Number) value).longValue();
        }
        if (value instanceof BigInteger big) {
            try {
                return big.longValueExact();
            } catch (ArithmeticException outOfRange) {
                return null;
            }
        }
        if (value instanceof BigDecimal big) {
            try {
                return big.longValueExact();
            } catch (ArithmeticException fractionalOrOutOfRange) {
                return null;
            }
        }
        if (value instanceof Float || value instanceof Double) {
            double converted = ((Number) value).doubleValue();
            // Long.MAX_VALUE rounds to 2^63 as a double; the upper bound must be exclusive.
            if (!Double.isFinite(converted) || converted != Math.rint(converted)
                    || converted < -0x1p63 || converted >= 0x1p63) {
                return null;
            }
            return (long) converted;
        }
        return null;
    }

    private static String text(Object value) {
        return value instanceof String string ? string : null;
    }

    private static Boolean flag(Object value) {
        return value instanceof Boolean bool ? bool : null;
    }

    private static List<MessageMetadataQuery.ExecutionStageQuery> stages(Object value) {
        if (!(value instanceof List<?> items)) {
            return null;
        }
        List<MessageMetadataQuery.ExecutionStageQuery> stages = new ArrayList<>(items.size());
        for (Object item : items) {
            if (item instanceof Map<?, ?> stage
                    && stage.get("stage") instanceof String stageName
                    && stage.get("status") instanceof String status
                    && stage.get("description") instanceof String description) {
                stages.add(new MessageMetadataQuery.ExecutionStageQuery(
                        stageName,
                        status,
                        description,
                        whole(stage.get("durationMs")),
                        terminal(stage.get("terminal")),
                        activity(stage.get("activity"))));
            }
        }
        return stages.isEmpty() ? null : stages;
    }

    /** Closed public slice of a persisted terminal payload; unexpected JSON types drop to null. */
    private static MessageMetadataQuery.TerminalQuery terminal(Object value) {
        if (!(value instanceof Map<?, ?> raw)) {
            return null;
        }
        return new MessageMetadataQuery.TerminalQuery(
                text(raw.get("command")),
                text(raw.get("cwd")),
                whole(raw.get("exitCode")),
                text(raw.get("stdout")),
                text(raw.get("stderr")),
                flag(raw.get("timedOut")),
                flag(raw.get("truncated")),
                whole(raw.get("durationMs")));
    }

    /** Closed public slice of a persisted activity payload; unexpected JSON types drop to null. */
    private static MessageMetadataQuery.ActivityQuery activity(Object value) {
        if (!(value instanceof Map<?, ?> raw)) {
            return null;
        }
        return new MessageMetadataQuery.ActivityQuery(
                text(raw.get("kind")),
                text(raw.get("status")),
                text(raw.get("capabilityId")),
                text(raw.get("relativePath")),
                text(raw.get("summary")),
                whole(raw.get("addedLines")),
                whole(raw.get("removedLines")),
                whole(raw.get("entryCount")),
                text(raw.get("errorCode")));
    }
}
