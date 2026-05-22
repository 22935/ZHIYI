package com.kinlin.ai.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.config.AgentProperties;
import com.kinlin.ai.service.AgentOsGatewayService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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
        private final Map<String, String> textResponses = new HashMap<>();
        private String lastGetPath;
        private String lastPostPath;
        private String lastTextPath;

        private RecordingAgentOsGatewayService() {
            super(WebClient.builder(), new AgentProperties(), "http://localhost:8000");
        }

        @Override
        public Map<String, Object> get(String path) {
            lastGetPath = path;
            return getResponses.getOrDefault(path, Map.of());
        }

        @Override
        public Map<String, Object> post(String path, Object body) {
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
