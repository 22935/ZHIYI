package com.kinlin.ai.projection.run;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.projection.run.mapper.RunActionCapabilitiesMapper;
import com.kinlin.ai.projection.run.mapper.RunProjectionMapper;
import com.kinlin.ai.projection.workspace.WorkspaceQueryFixture;
import com.kinlin.ai.projection.workspace.mapper.WorkspaceProjectionMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RunActionCapabilitiesProjectionTest {
    private Map<String, Object> offers() {
        var value = new LinkedHashMap<String, Object>();
        for (String action : List.of("canInspect", "canDiscuss", "canCancel", "canReview", "canExecuteFormalAction",
                "canResolveToolApproval", "canAnswerPlanner", "canCollaborate", "canRetrySuccessor",
                "canRerunSuccessor", "canDecideRevision", "canApplyRevision", "canDelete")) {
            value.put(action, false);
        }
        value.putAll(Map.of("schemaVersion", 1, "missionId", "mission_1", "runId", "run_1", "runtimeRevision", 7,
                "status", "running", "isExecutionActive", true, "isSuperseded", false,
                "lineage", Map.of("sourceRunId", "source", "privateGrant", "SECRET")));
        value.put("canCancel", true);
        value.put("formalActions", List.of());
        value.put("unavailableReasons", List.of(Map.of("action", "canReview", "code", "EVIDENCE_UNAVAILABLE", "private", "SECRET")));
        value.put("authorityToken", "SECRET");
        return value;
    }
    @Test void runAndWorkspacePreserveIndependentOffersThroughWhitelist() throws Exception {
        var cap = offers();
        var run = RunProjectionMapper.run(Map.of("runId", "run_1", "missionId", "mission_1", "status", "running",
                "runtimeRevision", 7, "actionCapabilities", cap));
        assertTrue(run.actionCapabilities().canCancel());
        assertFalse(run.actionCapabilities().canReview());
        var workspace = new LinkedHashMap<>(WorkspaceQueryFixture.normalPlan());
        var selected = new LinkedHashMap<>((Map<String, Object>) workspace.get("activeRun"));
        selected.put("actionCapabilities", cap);
        workspace.put("activeRun", selected);
        var mapped = WorkspaceProjectionMapper.workspace(workspace);
        assertTrue(mapped.activeRun().actionCapabilities().canCancel());
        assertEquals("source", mapped.activeRun().actionCapabilities().lineage().sourceRunId());
        assertFalse(new ObjectMapper().writeValueAsString(mapped).contains("SECRET"));
    }
    @Test void missingLegacyOffersRemainMissingAndMalformedOrForeignOffersFailClosed() {
        assertNull(RunActionCapabilitiesMapper.read(null, "run_1", "mission_1"));
        assertThrows(IllegalArgumentException.class, () -> RunActionCapabilitiesMapper.read(offers(), "other", "mission_1"));
        assertThrows(IllegalArgumentException.class, () -> RunActionCapabilitiesMapper.read(offers(), "run_1", "foreign"));
        var malformed = offers(); malformed.put("canCancel", "true");
        assertThrows(IllegalArgumentException.class, () -> RunActionCapabilitiesMapper.read(malformed, "run_1", "mission_1"));
        malformed.put("canCancel", true); malformed.remove("canReview");
        assertThrows(IllegalArgumentException.class, () -> RunActionCapabilitiesMapper.read(malformed, "run_1", "mission_1"));
    }
}
