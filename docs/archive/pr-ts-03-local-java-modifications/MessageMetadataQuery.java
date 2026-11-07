package com.kinlin.ai.projection.message.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

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
        @JsonInclude(JsonInclude.Include.NON_NULL) String reasoningContent,
        @JsonInclude(JsonInclude.Include.NON_NULL) Boolean reasoningTruncated,
        List<ExecutionStageQuery> executionSummary
) {

    /** One observable pipeline stage as persisted by the stream capture. */
    public record ExecutionStageQuery(
            String stage,
            String status,
            String description,
            Long durationMs,
            TerminalQuery terminal,
            ActivityQuery activity
    ) { }

    /** Closed public slice of a persisted command terminal payload. */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record TerminalQuery(
            String command,
            String cwd,
            Long exitCode,
            String stdout,
            String stderr,
            Boolean timedOut,
            Boolean truncated,
            Long durationMs
    ) { }

    /** Closed public slice of a persisted tool activity payload. */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ActivityQuery(
            String kind,
            String status,
            String capabilityId,
            String relativePath,
            String summary,
            Long addedLines,
            Long removedLines,
            Long entryCount,
            String errorCode
    ) { }
}
