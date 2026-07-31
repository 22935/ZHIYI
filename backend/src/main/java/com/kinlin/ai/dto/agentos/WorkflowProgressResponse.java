package com.kinlin.ai.dto.agentos;

import com.fasterxml.jackson.annotation.JsonFormat;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/** Typed pass-through contract for Python AgentOS workflow progress. */
public record WorkflowProgressResponse(
        String taskId,
        String runId,
        String workflowId,
        String status,
        String phase,
        String message,
        BigDecimal percent,
        Integer totalSteps,
        Integer pendingSteps,
        Integer runningSteps,
        Integer waitingReviewSteps,
        Integer retryingSteps,
        Integer failedSteps,
        Integer completedSteps,
        Integer cancelledSteps,
        String currentStepId,
        List<String> activeStepIds,
        Integer recoveryCount,
        Integer graphVersion,
        Integer dynamicStepCount,
        Integer bindingSwitchCount,
        Integer skippedByConditionCount,
        Integer conditionalDecisionCount,
        @JsonFormat(shape = JsonFormat.Shape.STRING) OffsetDateTime startedAt,
        @JsonFormat(shape = JsonFormat.Shape.STRING) OffsetDateTime updatedAt,
        BigDecimal progress,
        BigDecimal percentage
) {
    private static final Set<String> PHASES = Set.of(
            "understanding",
            "planning",
            "graph_building",
            "executing",
            "recovery",
            "review",
            "completed",
            "failed",
            "cancelled"
    );

    public WorkflowProgressResponse {
        Objects.requireNonNull(taskId, "taskId is required");
        Objects.requireNonNull(runId, "runId is required");
        Objects.requireNonNull(workflowId, "workflowId is required");
        Objects.requireNonNull(status, "status is required");
        Objects.requireNonNull(phase, "phase is required");
        Objects.requireNonNull(message, "message is required");
        Objects.requireNonNull(totalSteps, "totalSteps is required");
        Objects.requireNonNull(pendingSteps, "pendingSteps is required");
        Objects.requireNonNull(runningSteps, "runningSteps is required");
        Objects.requireNonNull(waitingReviewSteps, "waitingReviewSteps is required");
        Objects.requireNonNull(retryingSteps, "retryingSteps is required");
        Objects.requireNonNull(failedSteps, "failedSteps is required");
        Objects.requireNonNull(completedSteps, "completedSteps is required");
        Objects.requireNonNull(cancelledSteps, "cancelledSteps is required");
        Objects.requireNonNull(activeStepIds, "activeStepIds is required");
        Objects.requireNonNull(recoveryCount, "recoveryCount is required");
        Objects.requireNonNull(updatedAt, "updatedAt is required");
        Objects.requireNonNull(progress, "progress is required");
        Objects.requireNonNull(percentage, "percentage is required");
        if (!PHASES.contains(phase)) {
            throw new IllegalArgumentException("unsupported workflow progress phase");
        }
        activeStepIds = List.copyOf(activeStepIds);
    }
}
