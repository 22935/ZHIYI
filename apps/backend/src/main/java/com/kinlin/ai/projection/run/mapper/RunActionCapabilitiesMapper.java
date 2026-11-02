package com.kinlin.ai.projection.run.mapper;

import com.kinlin.ai.projection.run.dto.RunActionCapabilitiesQuery;
import java.util.Map;
import java.util.Set;
import static com.kinlin.ai.projection.common.mapper.QueryWire.*;

/** Whitelist only: no permission calculation, mutation or runtime lookup. */
public final class RunActionCapabilitiesMapper {
    private RunActionCapabilitiesMapper() { }
    private static Boolean flag(Map<?, ?> source, String name) {
        Boolean value = bool(source, name);
        if (value == null) { throw invalid(); }
        return value;
    }
    public static RunActionCapabilitiesQuery read(Object value, String runId, String missionId) {
        if (value == null) { return null; } // Older Agent hosts remain readable, with no offers.
        Map<?, ?> c = object(value);
        if (requiredInt(c, "schemaVersion") != 1 || !runId.equals(requiredText(c, "runId"))
                || missionId != null && !missionId.equals(requiredText(c, "missionId"))) { throw invalid(); }
        Long revision = integer(c, "runtimeRevision");
        if (revision == null || revision < 0) { throw invalid(); }
        var actions = texts(c.get("formalActions"));
        if (!Set.of("materialize", "activate", "handoff", "permit", "dispatch").containsAll(actions)) { throw invalid(); }
        return new RunActionCapabilitiesQuery(1, requiredText(c, "missionId"), requiredText(c, "runId"), revision,
                requiredText(c, "status"), flag(c, "isExecutionActive"), flag(c, "isSuperseded"),
                RunProjectionMapper.lineage(optionalObject(c.get("lineage"))),
                flag(c, "canInspect"), flag(c, "canDiscuss"), flag(c, "canCancel"), flag(c, "canReview"),
                flag(c, "canExecuteFormalAction"), actions, flag(c, "canResolveToolApproval"),
                flag(c, "canAnswerPlanner"), flag(c, "canCollaborate"), flag(c, "canRetrySuccessor"),
                text(c, "retryStepId"), flag(c, "canRerunSuccessor"), flag(c, "canDecideRevision"),
                flag(c, "canApplyRevision"), flag(c, "canDelete"), items(c.get("unavailableReasons"), reason ->
                    new RunActionCapabilitiesQuery.UnavailableReason(requiredText(reason, "action"), requiredText(reason, "code"))));
    }
}
