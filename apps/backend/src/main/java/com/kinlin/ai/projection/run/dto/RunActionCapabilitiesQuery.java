package com.kinlin.ai.projection.run.dto;

import java.util.List;

/** Server-computed UI offers for one Run. Never an execution grant. */
public record RunActionCapabilitiesQuery(
        Integer schemaVersion, String missionId, String runId, Long runtimeRevision,
        String status, Boolean isExecutionActive, Boolean isSuperseded, RunLineageQuery lineage,
        Boolean canInspect, Boolean canDiscuss, Boolean canCancel, Boolean canReview,
        Boolean canExecuteFormalAction, List<String> formalActions,
        Boolean canResolveToolApproval, Boolean canAnswerPlanner, Boolean canCollaborate,
        Boolean canRetrySuccessor, String retryStepId, Boolean canRerunSuccessor,
        Boolean canDecideRevision, Boolean canApplyRevision, Boolean canDelete,
        List<UnavailableReason> unavailableReasons
) {
    public RunActionCapabilitiesQuery {
        formalActions = List.copyOf(formalActions);
        unavailableReasons = List.copyOf(unavailableReasons);
    }
    public record UnavailableReason(String action, String code) { }
}
