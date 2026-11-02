package com.kinlin.ai.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.dto.agentos.AgentOsMissionRunCreateRequest;
import com.kinlin.ai.exception.AgentOsGatewayExceptionHandler;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import com.kinlin.ai.projection.run.dto.RunQuery;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** RUN ownership: mission-nested create, history filter list, read, cancel, soft delete. */
class AgentOsRunControllerTest {

    private MockMvc mockMvc;
    private ObjectMapper objectMapper;
    private RecordingAgentOsGateway gateway;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        gateway = new RecordingAgentOsGateway();
        mockMvc = MockMvcBuilders.standaloneSetup(new AgentOsRunController(gateway))
                .setControllerAdvice(new AgentOsGatewayExceptionHandler())
                .build();
    }

    @Test
    void formalControlProjectionPreservesPublicFactsWithoutPrivateLedgerFields() throws Exception {
        Map<String, Object> control = new LinkedHashMap<>();
        control.put("status", "ACTIVATED"); control.put("permitStatus", "ISSUED");
        control.put("dispatchEnabled", true); control.put("dispatchEligible", false);
        control.put("dispatch", Map.of("dispatchId", "d1", "runId", "run_1", "permitId", "p1", "graphVersion", 1,
                "status", "ACCEPTED", "actor_id", "private-owner", "signature", "private-signature"));
        control.put("checkpointPayload", Map.of("secret", "private-checkpoint"));
        gateway.getResponses.put("/ai/agentos/v2/runs/run_1", RecordingAgentOsGateway.response(200, Map.of(
                "runId", "run_1", "status", "pending", "formalControl", control,
                "error", Map.of("code", "DISPATCH_RECOVERY_BLOCKED", "signature", "private-audit"))));
        mockMvc.perform(get("/api/agentos/v2/runs/run_1")).andExpect(status().isOk())
                .andExpect(jsonPath("$.formalControl.dispatch.dispatchId").value("d1"))
                .andExpect(jsonPath("$.formalControl.dispatch.status").value("ACCEPTED"))
                .andExpect(jsonPath("$.formalControl.dispatch.actor_id").doesNotExist())
                .andExpect(jsonPath("$.formalControl.dispatch.signature").doesNotExist())
                .andExpect(jsonPath("$.formalControl.checkpointPayload").doesNotExist())
                .andExpect(jsonPath("$.failureCode").value("DISPATCH_RECOVERY_BLOCKED"))
                .andExpect(jsonPath("$.error").doesNotExist());
        control.put("dispatchEnabled", "not-a-boolean");
        mockMvc.perform(get("/api/agentos/v2/runs/run_1")).andExpect(status().isBadGateway());
    }

    @Test
    void createMissionRunPostsTheExactContractAndPreservesUpstreamStatus() throws Exception {
        String upstream = "/ai/agentos/v2/missions/mission%20001/runs";
        gateway.postResponses.put(upstream, RecordingAgentOsGateway.response(202, Map.of(
                "missionId", "mission 001", "runId", "run_002", "status", "pending"
        )));

        mockMvc.perform(post("/api/agentos/v2/missions/{missionId}/runs", "mission 001")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "workflowId", "workflow_1",
                                "reviewMode", "auto",
                                "input", Map.of("taskGoal", "再次执行"),
                                "enabledPluginIds", List.of("plugin_1"),
                                "clientRequestId", "rerun-request-1",
                                "sourceRunId", "run_001",
                                "rerunReason", "manual_rerun"
                        ))))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.runId").value("run_002"));

        assertEquals(upstream, gateway.lastPostPath);
        AgentOsMissionRunCreateRequest request = (AgentOsMissionRunCreateRequest) gateway.lastPostBody;
        assertEquals("run_001", request.sourceRunId());
        assertEquals("manual_rerun", request.rerunReason());
        assertEquals("再次执行", request.input().get("taskGoal"));
        assertEquals(List.of("plugin_1"), request.enabledPluginIds());
    }

    @Test
    void listRunsForwardsTheCompleteHistoryFilterContract() throws Exception {
        String upstream = "/ai/agentos/v2/runs?statuses=running,waiting_review&domain=legal"
                + "&workflowId=workflow_1&missionId=mission_1&lifecyclePhase=review&source=acg"
                + "&sources=acg,chat&recordState=archived&summary=true&page=2&pageSize=50";
        gateway.getResponses.put(upstream, RecordingAgentOsGateway.response(200, Map.of(
                "items", List.of(), "total", 0, "page", 2, "pageSize", 50
        )));

        mockMvc.perform(get("/api/agentos/v2/runs")
                        .param("statuses", "running,waiting_review")
                        .param("domain", "legal")
                        .param("workflowId", "workflow_1")
                        .param("missionId", "mission_1")
                        .param("lifecyclePhase", "review")
                        .param("source", "acg")
                        .param("sources", "acg,chat")
                        .param("recordState", "archived")
                        .param("summary", "true")
                        .param("page", "2")
                        .param("pageSize", "50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(0));

        assertEquals(upstream, gateway.lastGetPath);
    }

    @Test
    void getRunUsesEncodedRunIdentity() throws Exception {
        String path = "/ai/agentos/v2/runs/run%20001";
        gateway.getResponses.put(path, RecordingAgentOsGateway.response(200, Map.of(
                "runId", "run 001", "status", "running", "executionState", Map.of("checkpointId", "secret")
        )));

        mockMvc.perform(get("/api/agentos/v2/runs/{runId}", "run 001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("running"))
                .andExpect(jsonPath("$.executionState").doesNotExist())
                .andExpect(jsonPath("$.checkpointId").doesNotExist());

        assertInstanceOf(RunQuery.class, new AgentOsRunController(gateway).getRun("run 001").getBody());
        assertEquals(path, gateway.lastGetPath);
    }

    @Test
    void runCancellationForwardsOwnedRunSubresourceAndKeepsConflictStatus() throws Exception {
        String cancelPath = "/ai/agentos/v2/runs/run%20001/cancel";
        gateway.postResponses.put(cancelPath, RecordingAgentOsGateway.response(200, Map.of(
                "runId", "run_001", "status", "cancelled")));
        mockMvc.perform(post("/api/agentos/v2/runs/{runId}/cancel", "run 001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("cancelled"));
        assertEquals("/ai/agentos/v2/runs/run%20001/cancel", gateway.lastPostPath);

        String conflictPath = "/ai/agentos/v2/runs/run_002/cancel";
        gateway.postResponses.put(conflictPath, RecordingAgentOsGateway.response(409, new LinkedHashMap<>(Map.of(
                "detail", "run cannot be cancelled"))));
        mockMvc.perform(post("/api/agentos/v2/runs/{runId}/cancel", "run_002"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("AGENTOS_REQUEST_REJECTED"))
                .andExpect(jsonPath("$.message").value("run cannot be cancelled"));
        assertEquals(conflictPath, gateway.lastPostPath);
    }

    @Test
    void cancellationPreservesTheOptionalComparisonRevision() throws Exception {
        String path = "/ai/agentos/v2/runs/run_001/cancel";
        gateway.postResponses.put(path, RecordingAgentOsGateway.response(200, Map.of("runId", "run_001", "status", "cancelled")));
        mockMvc.perform(post("/api/agentos/v2/runs/run_001/cancel").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"expectedRuntimeRevision\":17}"))
                .andExpect(status().isOk());
        var request = assertInstanceOf(com.kinlin.ai.dto.agentos.AgentOsRunCancelRequest.class, gateway.lastPostBody);
        assertEquals(17L, request.expectedRuntimeRevision());
        mockMvc.perform(post("/api/agentos/v2/runs/run_001/cancel").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"expectedRuntimeRevision\":-1}"))
                .andExpect(status().isUnprocessableEntity());
    }

    @Test
    void runDeleteForwardsEncodedIdentityAndKeepsConflictStatus() throws Exception {
        String deletedPath = "/ai/agentos/v2/runs/run%20001";
        gateway.deleteResponses.put(deletedPath, RecordingAgentOsGateway.response(200, Map.of(
                "runId", "run 001", "recordState", "deleted", "deletedAt", "2026-10-06T00:00:00Z")));
        mockMvc.perform(delete("/api/agentos/v2/runs/{runId}", "run 001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.recordState").value("deleted"));
        assertEquals(deletedPath, gateway.lastDeletePath);

        String conflictPath = "/ai/agentos/v2/runs/run_002";
        gateway.deleteResponses.put(conflictPath, RecordingAgentOsGateway.response(409, new LinkedHashMap<>(Map.of(
                "detail", "run is not terminal"))));
        mockMvc.perform(delete("/api/agentos/v2/runs/{runId}", "run_002"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.detail").value("run is not terminal"));
        assertEquals(conflictPath, gateway.lastDeletePath);
    }
}
