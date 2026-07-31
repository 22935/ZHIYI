package com.kinlin.ai.controller;

import com.kinlin.ai.service.AgentOsGatewayService;
import com.kinlin.ai.dto.agentos.AsyncWorkflowStartRequest;
import com.kinlin.ai.dto.agentos.AsyncWorkflowStartResponse;
import com.kinlin.ai.dto.agentos.WorkflowProgressResponse;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriUtils;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/** AgentOS 核心网关代理控制器 — 映射 /api/agentos、/agentos、/ai，代理转发 AgentOS 任务创建/查询等 API */
@RestController
@RequestMapping({"/api/agentos", "/agentos", "/ai"})
@RequiredArgsConstructor
public class AgentOsGatewayController {

    private final AgentOsGatewayService agentOsGatewayService;

    @PostMapping(value = "/core/materials", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Map<String, Object>> uploadMaterial(
            @RequestParam("file") MultipartFile file
    ) {
        if (file.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "MATERIAL_EMPTY",
                    "message", "文件内容为空"
            ));
        }
        return gatewayResponse(agentOsGatewayService.postMaterial("/ai/core/materials", file));
    }

    @DeleteMapping("/core/materials/{materialId}")
    public ResponseEntity<Map<String, Object>> deleteMaterial(@PathVariable String materialId) {
        String safeId = UriUtils.encodePathSegment(materialId, StandardCharsets.UTF_8);
        return gatewayResponse(agentOsGatewayService.delete("/ai/core/materials/" + safeId));
    }

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
            @RequestParam(required = false) String statuses,
            @RequestParam(required = false) String domain,
            @RequestParam(required = false, name = "workflowId") String workflowId,
            @RequestParam(required = false, name = "taskId") String taskId,
            @RequestParam(required = false, name = "lifecyclePhase") String lifecyclePhase,
            @RequestParam(required = false) String source,
            @RequestParam(defaultValue = "false") boolean summary,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        return gatewayResponse(agentOsGatewayService.get(buildQuery("/ai/core/workflows/runs",
                mapOf(
                        "status", status,
                        "statuses", statuses,
                        "domain", domain,
                        "workflowId", workflowId,
                        "taskId", taskId,
                        "lifecyclePhase", lifecyclePhase,
                        "source", source,
                        "summary", summary ? "true" : null,
                        "page", String.valueOf(page),
                        "pageSize", String.valueOf(pageSize)
                ))));
    }

    @PostMapping("/core/workflows/start")
    public ResponseEntity<Map<String, Object>> startWorkflowFromWorkbench(@RequestBody(required = false) Map<String, Object> body) {
        return gatewayResponse(agentOsGatewayService.post("/ai/core/workflows/start", body));
    }

    @PostMapping("/core/workflows/start-async")
    public ResponseEntity<?> startWorkflowAsync(@RequestBody AsyncWorkflowStartRequest body) {
        Map<String, Object> upstream = agentOsGatewayService.postAsyncStart("/ai/core/workflows/start-async", body);
        Map<String, Object> response = new LinkedHashMap<>(upstream == null ? Map.of() : upstream);
        Object status = response.remove(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY);
        int httpStatus = status instanceof Number ? ((Number) status).intValue() : 200;
        if (httpStatus < 200 || httpStatus >= 300) {
            return ResponseEntity.status(httpStatus).body(response);
        }
        try {
            AsyncWorkflowStartResponse parsed = agentOsGatewayService.parseAsyncWorkflowStart(response);
            return ResponseEntity.status(httpStatus).body(parsed);
        } catch (IllegalStateException exception) {
            Map<String, Object> invalid = new LinkedHashMap<>();
            invalid.put("success", false);
            invalid.put("message", "AgentOS returned an invalid async start response.");
            invalid.put("error", "AGENTOS_INVALID_ASYNC_START_RESPONSE");
            return ResponseEntity.status(502).body(invalid);
        }
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

    @GetMapping("/core/workflows/runs/{runId}/progress")
    public ResponseEntity<?> getWorkflowProgress(HttpServletRequest request) {
        Map<String, Object> upstream = agentOsGatewayService.getProgress(toPythonPath(request));
        Map<String, Object> response = new LinkedHashMap<>(upstream == null ? Map.of() : upstream);
        Object status = response.remove(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY);
        int httpStatus = status instanceof Number ? ((Number) status).intValue() : 200;
        if (httpStatus < 200 || httpStatus >= 300) {
            return ResponseEntity.status(httpStatus).body(response);
        }
        try {
            WorkflowProgressResponse progress = agentOsGatewayService.parseWorkflowProgress(response);
            return ResponseEntity.ok(progress);
        } catch (IllegalStateException exception) {
            Map<String, Object> invalid = new LinkedHashMap<>();
            invalid.put("success", false);
            invalid.put("message", "AgentOS returned an invalid progress response.");
            invalid.put("error", "AGENTOS_INVALID_PROGRESS_RESPONSE");
            return ResponseEntity.status(502).body(invalid);
        }
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

    @GetMapping("/core/workflows/runs/{runId}/acg")
    public ResponseEntity<Map<String, Object>> getAcgView(HttpServletRequest request) {
        return gatewayResponse(agentOsGatewayService.get(toPythonPath(request)));
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
