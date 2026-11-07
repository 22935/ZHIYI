package com.kinlin.ai.projection.message.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * Whitelisted public slice of the persisted message metadata JSON.
 *
 * <p>Producers of the excluded internal keys (role_context, sources, reasoning_path,
 * agent_mode, toolExecutions, toolsUsed, fallbackUsed, resolutionReasons) still
 * persist them; they are not read back by any history consumer and therefore do
 * not enter the public response. Legacy snake_case keys keep their wire names.
 */
public record MessageMetadataQuery(
        Double confidence,
        @JsonProperty("tokens_used") Long tokensUsed,
        Long totalTokens,
        String effectiveModel,
        @JsonProperty("model_info") String modelInfo,
        String requestedThinkingMode,
        String effectiveThinkingMode,
        String effectiveReasoningEffort,
        Long reasoningPhaseMs,
        Long inputTokens,
        Long reasoningTokens,
        Long outputTokens,
        Long latencyMs,
        Boolean thinkingEnabled,
        List<ExecutionStageQuery> executionSummary
) {

    /** One observable pipeline stage as persisted by the stream capture. */
    public record ExecutionStageQuery(
            String stage,
            String status,
            String description,
            @JsonInclude(JsonInclude.Include.NON_NULL) Long durationMs,
            @JsonInclude(JsonInclude.Include.NON_NULL) Map<String, Object> terminal,
            @JsonInclude(JsonInclude.Include.NON_NULL) Map<String, Object> activity
    ) { }
}
