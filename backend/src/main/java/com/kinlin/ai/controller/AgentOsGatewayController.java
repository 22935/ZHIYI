package com.kinlin.ai.controller;

import com.kinlin.ai.service.AgentOsGatewayService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriUtils;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping({"/api/agentos", "/agentos", "/ai"})
@RequiredArgsConstructor
public class AgentOsGatewayController {

    private final AgentOsGatewayService agentOsGatewayService;

    @PostMapping("/core/tasks")
    public ResponseEntity<Map<String, Object>> createTask(@RequestBody(required = false) Map<String, Object> body) {
        return gatewayResponse(agentOsGatewayService.post("/ai/core/tasks", body));
    }

    @GetMapping("/core/tasks")
    public ResponseEntity<Map<String, Object>> listTasks(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String domain,
            @RequestParam(required = false) String source,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        return gatewayResponse(agentOsGatewayService.get(buildQuery("/ai/core/tasks",
                mapOf(
                        "status", status,
                        "domain", domain,
                        "source", source,
                        "page", String.valueOf(page),
                        "pageSize", String.valueOf(pageSize)
                ))));
    }

    @PostMapping("/core/workflows/runs")
    public ResponseEntity<Map<String, Object>> startWorkflow(@RequestBody(required = false) Map<String, Object> body) {
        return gatewayResponse(agentOsGatewayService.post("/ai/core/workflows/runs", body));
    }

    @GetMapping("/core/workflows/runs")
    public ResponseEntity<Map<String, Object>> listWorkflowRuns(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String domain,
            @RequestParam(required = false, name = "workflowId") String workflowId,
            @RequestParam(required = false) String source,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        return gatewayResponse(agentOsGatewayService.get(buildQuery("/ai/core/workflows/runs",
                mapOf(
                        "status", status,
                        "domain", domain,
                        "workflowId", workflowId,
                        "source", source,
                        "page", String.valueOf(page),
                        "pageSize", String.valueOf(pageSize)
                ))));
    }

    @PostMapping("/core/workflows/start")
    public ResponseEntity<Map<String, Object>> startWorkflowFromWorkbench(@RequestBody(required = false) Map<String, Object> body) {
        return gatewayResponse(agentOsGatewayService.post("/ai/core/workflows/start", body));
    }

    @GetMapping("/core/workflows/metrics")
    public ResponseEntity<Map<String, Object>> evaluateWorkflows(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String domain,
            @RequestParam(required = false, name = "workflowId") String workflowId,
            @RequestParam(required = false) String source
    ) {
        return gatewayResponse(agentOsGatewayService.get(buildQuery("/ai/core/workflows/metrics",
                mapOf(
                        "status", status,
                        "domain", domain,
                        "workflowId", workflowId,
                        "source", source
                ))));
    }

    @PostMapping("/chat/workflows/upgrade")
    public ResponseEntity<Map<String, Object>> upgradeChat(@RequestBody(required = false) Map<String, Object> body) {
        return gatewayResponse(agentOsGatewayService.post("/ai/chat/workflows/upgrade", body));
    }

    @GetMapping("/core/workflows/runs/{runId}")
    public ResponseEntity<Map<String, Object>> getWorkflowRun(HttpServletRequest request) {
        return gatewayResponse(agentOsGatewayService.get(toPythonPath(request)));
    }

    @GetMapping("/core/workflows/runs/{runId}/checkpoints")
    public ResponseEntity<Map<String, Object>> listCheckpoints(HttpServletRequest request) {
        return gatewayResponse(agentOsGatewayService.get(toPythonPath(request)));
    }

    @GetMapping("/core/workflows/runs/{runId}/trace")
    public ResponseEntity<?> exportWorkflowTrace(
            HttpServletRequest request,
            @RequestParam(defaultValue = "json") String format
    ) {
        String path = buildQuery(toPythonPath(request), mapOf("format", format));
        if ("markdown".equalsIgnoreCase(format)) {
            ResponseEntity<String> response = agentOsGatewayService.getTextResponse(path);
            return ResponseEntity.status(response.getStatusCode())
                    .contentType(MediaType.parseMediaType("text/markdown;charset=UTF-8"))
                    .body(response.getBody());
        }
        return gatewayResponse(agentOsGatewayService.get(path));
    }

    @GetMapping("/core/workflows/runs/{runId}/reviews")
    public ResponseEntity<Map<String, Object>> listReviews(HttpServletRequest request) {
        return gatewayResponse(agentOsGatewayService.get(toPythonPath(request)));
    }

    @PostMapping("/core/workflows/runs/{runId}/reviews")
    public ResponseEntity<Map<String, Object>> applyReview(HttpServletRequest request, @RequestBody(required = false) Map<String, Object> body) {
        return gatewayResponse(agentOsGatewayService.post(toPythonPath(request), body));
    }

    @PostMapping("/core/workflows/runs/{runId}/resume")
    public ResponseEntity<Map<String, Object>> resumeWorkflow(HttpServletRequest request, @RequestBody(required = false) Map<String, Object> body) {
        return gatewayResponse(agentOsGatewayService.post(toPythonPath(request), body));
    }

    @PostMapping("/core/workflows/runs/{runId}/cancel")
    public ResponseEntity<Map<String, Object>> cancelWorkflow(HttpServletRequest request) {
        return gatewayResponse(agentOsGatewayService.post(toPythonPath(request), Map.of()));
    }

    private String buildQuery(String basePath, Map<String, String> params) {
        StringBuilder sb = new StringBuilder(basePath);
        boolean first = true;
        for (Map.Entry<String, String> entry : params.entrySet()) {
            if (entry.getValue() == null || entry.getValue().isBlank()) {
                continue;
            }
            sb.append(first ? "?" : "&");
            first = false;
            sb.append(entry.getKey()).append("=").append(UriUtils.encodeQueryParam(entry.getValue(), StandardCharsets.UTF_8));
        }
        return sb.toString();
    }

    private String toPythonPath(HttpServletRequest request) {
        String path = request.getRequestURI();
        String contextPath = request.getContextPath();
        if (contextPath != null && !contextPath.isBlank()) {
            path = path.substring(contextPath.length());
        }
        if (path.startsWith("/api/agentos")) {
            return path.replaceFirst("/api/agentos", "/ai");
        }
        if (path.startsWith("/ai")) {
            return path;
        }
        return path.replaceFirst("/agentos", "/ai");
    }

    private Map<String, String> mapOf(String... entries) {
        Map<String, String> map = new LinkedHashMap<>();
        for (int i = 0; i < entries.length; i += 2) {
            map.put(entries[i], entries[i + 1]);
        }
        return map;
    }

    private ResponseEntity<Map<String, Object>> gatewayResponse(Map<String, Object> body) {
        Map<String, Object> response = new LinkedHashMap<>(body == null ? Map.of() : body);
        Object status = response.remove(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY);
        int httpStatus = status instanceof Number ? ((Number) status).intValue() : 200;
        return ResponseEntity.status(httpStatus).body(response);
    }
}
