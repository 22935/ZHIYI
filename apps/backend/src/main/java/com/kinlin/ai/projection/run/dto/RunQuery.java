package com.kinlin.ai.projection.run.dto;

import java.util.List;
import com.kinlin.ai.projection.common.dto.QueryResponse;

/** Explicit observation fields; never an executable runtime snapshot. */
public record RunQuery(
        String runId,
        String missionId,
        String title,
        String workflowId,
        String domain,
        String source,
        String runtimeEngine,
        String status,
        String lifecyclePhase,
        String lifecycleMessage,
        String currentStepId,
        List<String> completedStepIds,
        List<String> activeStepIds,
        List<String> skippedStepIds,
        String outputRef,
        Long runtimeRevision,
        List<StepQuery> steps,
        String createdAt,
        String updatedAt,
        String startedAt,
        Integer graphVersion,
        ReviewStateQuery review,
        RunLineageQuery lineage,
        List<OutputReferenceQuery> outputs,
        String planningDiversity,
        Long planningSeed,
        String plannerAlgorithmVersion,
        Integer planningCandidateCount,
        String selectedPlanningVariantId,
        FormalControlQuery formalControl,
        String failureCode,
        RunActionCapabilitiesQuery actionCapabilities
) implements QueryResponse {
    public RunQuery {
        completedStepIds = List.copyOf(completedStepIds);
        activeStepIds = List.copyOf(activeStepIds);
        skippedStepIds = List.copyOf(skippedStepIds);
        steps = List.copyOf(steps);
        outputs = List.copyOf(outputs);
    }
 }
