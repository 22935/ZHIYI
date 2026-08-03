package com.kinlin.ai.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.config.AgentProperties;
import com.kinlin.ai.service.AgentOsGatewayService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class AgentOsGatewayControllerTest {

    private MockMvc mockMvc;
    private ObjectMapper objectMapper;
    private RecordingAgentOsGatewayService agentOsGatewayService;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        agentOsGatewayService = new RecordingAgentOsGatewayService();
        mockMvc = MockMvcBuilders
                .standaloneSetup(new AgentOsGatewayController(agentOsGatewayService))
                .build();
    }

    private static class RecordingAgentOsGatewayService extends AgentOsGatewayService {
        private final Map<String, Map<String, Object>> getResponses = new HashMap<>();
        private final Map<String, Map<String, Object>> postResponses = new HashMap<>();
        private final Map<String, Map<String, Object>> asyncPostResponses = new HashMap<>();
        private final Map<String, String> textResponses = new HashMap<>();
        private String lastGetPath;
        private String lastPostPath;
        private Object lastPostBody;
        private Object lastAsyncPostBody;
        private String lastTextPath;
        private MultipartFile lastMaterialFile;

        private RecordingAgentOsGatewayService() {
            super(WebClient.builder(), new AgentProperties(), "http://localhost:8000");
        }

        @Override
        public Map<String, Object> get(String path) {
            lastGetPath = path;
            return getResponses.getOrDefault(path, Map.of());
        }

        @Override
        public Map<String, Object> getProgress(String path) {
            return get(path);
        }

        @Override
        public Map<String, Object> post(String path, Object body) {
            lastPostPath = path;
            lastPostBody = body;
            return postResponses.getOrDefault(path, Map.of());
        }

        @Override
        public Map<String, Object> postAsyncStart(String path, Object body) {
            lastPostPath = path;
            lastAsyncPostBody = body;
            return asyncPostResponses.getOrDefault(path, Map.of());
        }

        @Override
        public Map<String, Object> postMaterial(String path, MultipartFile file) {
            lastPostPath = path;
            lastMaterialFile = file;
            return postResponses.getOrDefault(path, Map.of());
        }

        @Override
        public Map<String, Object> delete(String path) {
            lastPostPath = path;
            return postResponses.getOrDefault(path, Map.of());
        }

        @Override
        public String getText(String path) {
            lastTextPath = path;
            return textResponses.getOrDefault(path, "");
        }

        @Override
        public ResponseEntity<String> getTextResponse(String path) {
            lastTextPath = path;
            return ResponseEntity.ok(textResponses.getOrDefault(path, ""));
        }
    }

    @Test
    void startWorkflow_forwardsToAgentOsCore() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("run", Map.of("runId", "run_001", "status", "waiting_review"));

        agentOsGatewayService.postResponses.put("/ai/core/workflows/start", response);

        Map<String, Object> request = Map.of(
                "title", "合同审查",
                "domain", "legal",
                "intent", "contract_review"
        );

        mockMvc.perform(post("/api/agentos/core/workflows/start")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.runId").value("run_001"))
                .andExpect(jsonPath("$.run.status").value("waiting_review"));

        assertEquals("/ai/core/workflows/start", agentOsGatewayService.lastPostPath);
    }

    @Test
    void startWorkflow_acceptsFrontendAiPathAndForwardsToAgentOsCore() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("run", Map.of("runId", "run_001", "status", "waiting_review"));

        agentOsGatewayService.postResponses.put("/ai/core/workflows/start", response);

        Map<String, Object> request = Map.of(
                "title", "合同审查",
                "domain", "legal",
                "intent", "contract_review"
        );

        mockMvc.perform(post("/ai/core/workflows/start")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.runId").value("run_001"))
                .andExpect(jsonPath("$.run.status").value("waiting_review"));

        assertEquals("/ai/core/workflows/start", agentOsGatewayService.lastPostPath);
    }

    @Test
    void startWorkflow_propagatesGatewayErrorStatus() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("success", false);
        response.put("message", "workflow not found");
        response.put(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 404);

        agentOsGatewayService.postResponses.put("/ai/core/workflows/start", response);

        mockMvc.perform(post("/api/agentos/core/workflows/start")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("workflowId", "missing"))))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value("workflow not found"))
                .andExpect(jsonPath("$._httpStatus").doesNotExist());
    }

    @Test
    void listWorkflowRuns_forwardsFiltersToAgentOsCore() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("total", 1);
        response.put("items", java.util.List.of(Map.of("runId", "run_001")));

        agentOsGatewayService.getResponses.put(
                "/ai/core/workflows/runs?status=waiting_review&source=workbench&page=1&pageSize=10",
                response
        );

        mockMvc.perform(get("/api/agentos/core/workflows/runs")
                        .param("status", "waiting_review")
                        .param("source", "workbench")
                        .param("page", "1")
                        .param("pageSize", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].runId").value("run_001"));

        assertEquals(
                "/ai/core/workflows/runs?status=waiting_review&source=workbench&page=1&pageSize=10",
                agentOsGatewayService.lastGetPath
        );
    }

    @Test
    void upgradeChat_forwardsToAgentOsChatUpgrade() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("source", "chat");
        response.put("run", Map.of("status", "waiting_review"));

        agentOsGatewayService.postResponses.put("/ai/chat/workflows/upgrade", response);

        mockMvc.perform(post("/api/agentos/chat/workflows/upgrade")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "聊天升级案件分析"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.source").value("chat"))
                .andExpect(jsonPath("$.run.status").value("waiting_review"));

        assertEquals("/ai/chat/workflows/upgrade", agentOsGatewayService.lastPostPath);
    }

    @Test
    void exportWorkflowTrace_forwardsJsonExportToAgentOsCore() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("runId", "run_001");
        response.put("eventCount", 2);

        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_001/trace?format=json", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/trace"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId").value("run_001"))
                .andExpect(jsonPath("$.eventCount").value(2));

        assertEquals("/ai/core/workflows/runs/run_001/trace?format=json", agentOsGatewayService.lastGetPath);
    }

    @Test
    void exportWorkflowTrace_forwardsMarkdownExportToAgentOsCore() throws Exception {
        agentOsGatewayService.textResponses.put(
                "/ai/core/workflows/runs/run_001/trace?format=markdown",
                "# Workflow Trace: run_001\n"
        );

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/trace")
                        .param("format", "markdown"))
                .andExpect(status().isOk())
                .andExpect(content().string("# Workflow Trace: run_001\n"));

        assertEquals("/ai/core/workflows/runs/run_001/trace?format=markdown", agentOsGatewayService.lastTextPath);
    }

    @Test
    void listCheckpoints_forwardsToAgentOsCore() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("runId", "run_001");
        response.put("total", 1);

        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_001/checkpoints", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/checkpoints"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId").value("run_001"))
                .andExpect(jsonPath("$.total").value(1));

        assertEquals("/ai/core/workflows/runs/run_001/checkpoints", agentOsGatewayService.lastGetPath);
    }

    @Test
    void uploadMaterialAcceptsARealMultipartFileAndPreserves201() throws Exception {
        agentOsGatewayService.postResponses.put("/ai/core/materials", new LinkedHashMap<>(Map.of(
                AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 201,
                "materialId", "mat_123",
                "state", "ready"
        )));
        MockMultipartFile file = new MockMultipartFile(
                "file", "合同.txt", "text/plain", "合同正文".getBytes(java.nio.charset.StandardCharsets.UTF_8)
        );

        mockMvc.perform(multipart("/ai/core/materials").file(file))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.materialId").value("mat_123"));

        assertEquals("/ai/core/materials", agentOsGatewayService.lastPostPath);
        assertEquals("合同.txt", agentOsGatewayService.lastMaterialFile.getOriginalFilename());
    }

    @Test
    void uploadMaterialRejectsMissingFilePartWith422() throws Exception {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new AgentOsGatewayController(agentOsGatewayService))
                .setControllerAdvice(new com.kinlin.ai.exception.GlobalExceptionHandler())
                .build();

        mockMvc.perform(multipart("/ai/core/materials"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error").value("MATERIAL_FILE_REQUIRED"));
    }

    @Test
    void deleteMaterialForwardsOpaqueId() throws Exception {
        agentOsGatewayService.postResponses.put("/ai/core/materials/mat_123", new LinkedHashMap<>(Map.of(
                AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 204
        )));
        mockMvc.perform(delete("/ai/core/materials/mat_123"))
                .andExpect(status().isNoContent());
        assertEquals("/ai/core/materials/mat_123", agentOsGatewayService.lastPostPath);
    }

    @Test
    void listWorkflowRuns_forwardsLightweightControlPlaneFilters() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("total", 1);
        response.put("items", java.util.List.of(Map.of(
                "runId", "run_001",
                "phase", "review",
                "percent", 50.0
        )));
        String path = "/ai/core/workflows/runs?statuses=running,waiting_review"
                + "&taskId=task_001&lifecyclePhase=review&sources=agent,chat&summary=true&page=1&pageSize=50";
        agentOsGatewayService.getResponses.put(path, response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs")
                        .param("statuses", "running,waiting_review")
                        .param("sources", "agent,chat")
                        .param("taskId", "task_001")
                        .param("lifecyclePhase", "review")
                        .param("summary", "true")
                        .param("page", "1")
                        .param("pageSize", "50"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].phase").value("review"))
                .andExpect(jsonPath("$.items[0].percent").value(50.0));

        assertEquals(path, agentOsGatewayService.lastGetPath);
    }

    @Test
    void startWorkflowAsync_preserves202RunIdAndClientRequestId() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("accepted", true);
        response.put("task", Map.of("taskId", "task_001", "status", "pending", "title", "合同审查"));
        Map<String, Object> run = new LinkedHashMap<>();
        run.put("runId", "run_001");
        run.put("workflowId", "legal_contract_review_v1");
        run.put("status", "pending");
        run.put("lifecyclePhase", "understanding");
        run.put("lifecycleMessage", "任务已接受");
        run.put("steps", java.util.List.of());
        response.put("run", run);
        response.put(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 202);
        agentOsGatewayService.asyncPostResponses.put("/ai/core/workflows/start-async", response);

        mockMvc.perform(post("/api/agentos/core/workflows/start-async")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "title", "合同审查",
                                "domain", "legal",
                                "intent", "contract_review",
                                "clientRequestId", "frontend-request-1"
                        ))))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(jsonPath("$.acgTaskId").value("run_001"))
                .andExpect(jsonPath("$.run.runId").value("run_001"))
                .andExpect(jsonPath("$.run.workflowId").value("legal_contract_review_v1"))
                .andExpect(jsonPath("$.run.lifecyclePhase").value("understanding"));

        assertEquals("/ai/core/workflows/start-async", agentOsGatewayService.lastPostPath);
        com.kinlin.ai.dto.agentos.AsyncWorkflowStartRequest request =
                (com.kinlin.ai.dto.agentos.AsyncWorkflowStartRequest) agentOsGatewayService.lastAsyncPostBody;
        assertEquals("frontend-request-1", request.clientRequestId());
        assertEquals("internal", request.securityLevel());
        assertEquals("normal", request.priority());
        assertEquals("auto", request.reviewMode());
        assertEquals("stable", request.planningDiversity());
        assertEquals(null, request.planningSeed());
        assertEquals(Map.of(), request.input());
    }

    @Test
    void startWorkflowAsync_preserves409And503() throws Exception {
        Map<String, Object> conflict = new LinkedHashMap<>();
        conflict.put("detail", "clientRequestId conflict");
        conflict.put(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 409);
        agentOsGatewayService.asyncPostResponses.put("/ai/core/workflows/start-async", conflict);

        mockMvc.perform(post("/api/agentos/core/workflows/start-async")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("clientRequestId", "request-1"))))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.detail").value("clientRequestId conflict"));

        Map<String, Object> unavailable = new LinkedHashMap<>();
        unavailable.put("message", "upstream unavailable");
        unavailable.put(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 503);
        agentOsGatewayService.asyncPostResponses.put("/ai/core/workflows/start-async", unavailable);

        mockMvc.perform(post("/api/agentos/core/workflows/start-async")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("clientRequestId", "request-2"))))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.message").value("upstream unavailable"));
    }

    @Test
    void startWorkflowAsync_rejectsMissingRunIdAsGatewayContractError() throws Exception {
        Map<String, Object> invalid = new LinkedHashMap<>();
        invalid.put("accepted", true);
        invalid.put("task", Map.of("taskId", "task_001", "status", "pending"));
        invalid.put("run", Map.of("status", "pending"));
        invalid.put(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 202);
        agentOsGatewayService.asyncPostResponses.put("/ai/core/workflows/start-async", invalid);

        mockMvc.perform(post("/api/agentos/core/workflows/start-async")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("clientRequestId", "request-1"))))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error").value("AGENTOS_INVALID_ASYNC_START_RESPONSE"));
    }

    @Test
    void getAcgView_forwardsToAgentOsCore() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("runId", "run_001");
        response.put("engine", "acg");
        response.put("lowEntropyMetrics", Map.of("tokensSaved", 42));

        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_001/acg", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/acg"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId").value("run_001"))
                .andExpect(jsonPath("$.engine").value("acg"))
                .andExpect(jsonPath("$.lowEntropyMetrics.tokensSaved").value(42));

        assertEquals("/ai/core/workflows/runs/run_001/acg", agentOsGatewayService.lastGetPath);
    }

    @Test
    void getWorkflowProgress_forwardsTypedExecutingPayload() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("taskId", "task_001");
        response.put("runId", "run_001");
        response.put("workflowId", "legal_contract_review_v1");
        response.put("status", "running");
        response.put("phase", "executing");
        response.put("message", "正在执行步骤：risk_detect");
        response.put("percent", 42.86);
        response.put("totalSteps", 7);
        response.put("pendingSteps", 3);
        response.put("runningSteps", 1);
        response.put("waitingReviewSteps", 0);
        response.put("retryingSteps", 0);
        response.put("failedSteps", 0);
        response.put("completedSteps", 3);
        response.put("cancelledSteps", 0);
        response.put("currentStepId", "risk_detect");
        response.put("activeStepIds", java.util.List.of("risk_detect", "legal_match"));
        response.put("recoveryCount", 0);
        response.put("graphVersion", 2);
        response.put("dynamicStepCount", 2);
        response.put("bindingSwitchCount", 1);
        response.put("skippedByConditionCount", 2);
        response.put("conditionalDecisionCount", 1);
        response.put("startedAt", "2026-07-22T01:06:26Z");
        response.put("updatedAt", "2026-07-22T01:07:20Z");
        response.put("progress", 0.4286);
        response.put("percentage", 42.86);
        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_001/progress", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/progress"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId").value("run_001"))
                .andExpect(jsonPath("$.phase").value("executing"))
                .andExpect(jsonPath("$.percent").value(42.86))
                .andExpect(jsonPath("$.activeStepIds[0]").value("risk_detect"))
                .andExpect(jsonPath("$.activeStepIds[1]").value("legal_match"))
                .andExpect(jsonPath("$.graphVersion").value(2))
                .andExpect(jsonPath("$.dynamicStepCount").value(2))
                .andExpect(jsonPath("$.bindingSwitchCount").value(1))
                .andExpect(jsonPath("$.skippedByConditionCount").value(2))
                .andExpect(jsonPath("$.conditionalDecisionCount").value(1))
                .andExpect(jsonPath("$.startedAt").value("2026-07-22T01:06:26Z"))
                .andExpect(jsonPath("$.updatedAt").value("2026-07-22T01:07:20Z"));

        assertEquals("/ai/core/workflows/runs/run_001/progress", agentOsGatewayService.lastGetPath);
    }

    @Test
    void getWorkflowProgress_preservesNullPercent() throws Exception {
        Map<String, Object> response = progressResponse("planning");
        response.put("percent", null);
        response.put("progress", 0.0);
        response.put("percentage", 0.0);
        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_001/progress", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/progress"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.phase").value("planning"))
                .andExpect(jsonPath("$.percent").doesNotExist())
                .andExpect(jsonPath("$.progress").value(0.0));
    }

    @Test
    void getWorkflowProgress_preservesUpstream404() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("detail", "workflow run not found: run_missing");
        response.put(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 404);
        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_missing/progress", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_missing/progress"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value("workflow run not found: run_missing"))
                .andExpect(jsonPath("$._httpStatus").doesNotExist());
    }

    @Test
    void getWorkflowProgress_preservesCancelledStatusAndPhase() throws Exception {
        Map<String, Object> response = progressResponse("cancelled");
        response.put("status", "cancelled");
        response.put("percent", 25.0);
        response.put("progress", 0.25);
        response.put("percentage", 25.0);
        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_001/progress", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/progress"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("cancelled"))
                .andExpect(jsonPath("$.phase").value("cancelled"))
                .andExpect(jsonPath("$.percent").value(25.0));
    }

    @Test
    void getWorkflowProgress_rejectsInvalidPayloadWithoutFakingNormalProgress() throws Exception {
        Map<String, Object> response = progressResponse("not_a_phase");
        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_001/progress", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/progress"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error").value("AGENTOS_INVALID_PROGRESS_RESPONSE"))
                .andExpect(jsonPath("$.phase").doesNotExist());
    }

    private Map<String, Object> progressResponse(String phase) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("taskId", "task_001");
        response.put("runId", "run_001");
        response.put("workflowId", "workflow_001");
        response.put("status", "running");
        response.put("phase", phase);
        response.put("message", "planning");
        response.put("percent", 0.0);
        response.put("totalSteps", 0);
        response.put("pendingSteps", 0);
        response.put("runningSteps", 0);
        response.put("waitingReviewSteps", 0);
        response.put("retryingSteps", 0);
        response.put("failedSteps", 0);
        response.put("completedSteps", 0);
        response.put("cancelledSteps", 0);
        response.put("currentStepId", null);
        response.put("activeStepIds", java.util.List.of());
        response.put("recoveryCount", 0);
        response.put("startedAt", "2026-07-22T01:06:26Z");
        response.put("updatedAt", "2026-07-22T01:07:20Z");
        response.put("progress", 0.0);
        response.put("percentage", 0.0);
        return response;
    }

    @Test
    void listReviews_forwardsToAgentOsCore() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("runId", "run_001");
        response.put("total", 1);

        agentOsGatewayService.getResponses.put("/ai/core/workflows/runs/run_001/reviews", response);

        mockMvc.perform(get("/api/agentos/core/workflows/runs/run_001/reviews"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId").value("run_001"))
                .andExpect(jsonPath("$.total").value(1));

        assertEquals("/ai/core/workflows/runs/run_001/reviews", agentOsGatewayService.lastGetPath);
    }

    @Test
    void applyReview_preservesConflictAndOperationPayload() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("detail", "workflow run revision changed");
        response.put(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY, 409);
        agentOsGatewayService.postResponses.put("/ai/core/workflows/runs/run_001/reviews", response);

        Map<String, Object> request = new LinkedHashMap<>();
        request.put("stepId", "human_review");
        request.put("decision", "approved");
        request.put("operationId", "operation_001");
        request.put("expectedRunUpdatedAt", "2026-07-22T01:07:20Z");
        request.put("expectedStepStatus", "waiting_review");

        mockMvc.perform(post("/api/agentos/core/workflows/runs/run_001/reviews")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.detail").value("workflow run revision changed"));

        assertEquals(request, agentOsGatewayService.lastPostBody);
    }

    @Test
    void evaluateWorkflows_forwardsFiltersToAgentOsCore() throws Exception {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("workflowId", "legal_contract_review_v1");
        response.put("metrics", Map.of("totalRuns", 1));

        agentOsGatewayService.getResponses.put(
                "/ai/core/workflows/metrics?domain=legal&workflowId=legal_contract_review_v1",
                response
        );

        mockMvc.perform(get("/api/agentos/core/workflows/metrics")
                        .param("domain", "legal")
                        .param("workflowId", "legal_contract_review_v1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.workflowId").value("legal_contract_review_v1"))
                .andExpect(jsonPath("$.metrics.totalRuns").value(1));

        assertEquals(
                "/ai/core/workflows/metrics?domain=legal&workflowId=legal_contract_review_v1",
                agentOsGatewayService.lastGetPath
        );
    }
}
