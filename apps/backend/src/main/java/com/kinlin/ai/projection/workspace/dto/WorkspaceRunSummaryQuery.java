package com.kinlin.ai.projection.workspace.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.kinlin.ai.projection.run.dto.RunActionCapabilitiesQuery;

/**
 * Run history row; upstream WorkspaceRunSummary is already a clean projection and every
 * field maps verbatim. {@code parentRunId}/{@code sourceRunId} are public rerun lineage
 * labels extracted from run metadata; all other run-metadata keys stay internal.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record WorkspaceRunSummaryQuery(
        String runId,
        String status,
        String parentRunId,
        String sourceRunId,
        String createdAt,
        String completedAt,
        Boolean isActive,
        RunActionCapabilitiesQuery actionCapabilities
) {
    public WorkspaceRunSummaryQuery(String runId, String status, String parentRunId, String sourceRunId,
            String createdAt, String completedAt, Boolean isActive) {
        this(runId, status, parentRunId, sourceRunId, createdAt, completedAt, isActive, null);
    }
}
