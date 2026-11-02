package com.kinlin.ai.controller;

import com.kinlin.ai.client.AgentOsClient;
import com.kinlin.ai.dto.agentos.AgentOsApiResponse;
import com.kinlin.ai.dto.agentos.AgentOsMissionRunCreateRequest;
import com.kinlin.ai.dto.agentos.AgentOsOperationResponse;
import com.kinlin.ai.dto.agentos.AgentOsRunResponse;
import com.kinlin.ai.dto.agentos.AgentOsRunCancelRequest;
import com.kinlin.ai.gateway.AgentOsPaths;
import com.kinlin.ai.projection.common.dto.QueryResponse;
import com.kinlin.ai.projection.run.mapper.RunProjectionMapper;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * RUN ownership: run create (the route is mission-nested, the lifecycle is a
 * run's), run read / list with the complete history filter contract, cancel,
 * and soft delete.
 */
@RestController
@RequestMapping("/api/agentos/v2")
public class AgentOsRunController {

    private final AgentOsClient gateway;

    public AgentOsRunController(AgentOsClient gateway) {
        this.gateway = gateway;
    }

    @PostMapping("/missions/{missionId}/runs")
    public ResponseEntity<? extends AgentOsApiResponse> createMissionRun(
            @PathVariable String missionId,
            @Valid @RequestBody AgentOsMissionRunCreateRequest body
    ) {
        return AgentOsControllerSupport.typedResponse(gateway.postTyped(
                AgentOsPaths.missionRuns(missionId), body, AgentOsRunResponse.class
        ));
    }

    @GetMapping("/runs")
    public ResponseEntity<QueryResponse> listRuns(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String statuses,
            @RequestParam(required = false) String domain,
            @RequestParam(required = false) String workflowId,
            @RequestParam(required = false) String missionId,
            @RequestParam(required = false) String lifecyclePhase,
            @RequestParam(required = false) String source,
            @RequestParam(required = false) String sources,
            @RequestParam(required = false) String recordState,
            @RequestParam(required = false) Boolean summary,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        Map<String, String> params = new LinkedHashMap<>();
        params.put("status", status);
        params.put("statuses", statuses);
        params.put("domain", domain);
        params.put("workflowId", workflowId);
        params.put("missionId", missionId);
        params.put("lifecyclePhase", lifecyclePhase);
        params.put("source", source);
        params.put("sources", sources);
        params.put("recordState", recordState);
        params.put("summary", summary == null ? null : summary.toString());
        params.put("page", String.valueOf(page));
        params.put("pageSize", String.valueOf(pageSize));
        return AgentOsControllerSupport.projectedResponse(
                gateway.get(AgentOsPaths.query(AgentOsPaths.runs(), params)), RunProjectionMapper::page);
    }

    @GetMapping("/runs/{runId}")
    public ResponseEntity<QueryResponse> getRun(@PathVariable String runId) {
        return AgentOsControllerSupport.projectedResponse(gateway.get(AgentOsPaths.run(runId)), RunProjectionMapper::run);
    }

    @PostMapping("/runs/{runId}/cancel")
    public ResponseEntity<? extends AgentOsApiResponse> cancelRun(@PathVariable String runId,
            @Valid @RequestBody(required = false) AgentOsRunCancelRequest request) {
        return AgentOsControllerSupport.typedResponse(gateway.postTyped(
                AgentOsPaths.run(runId) + "/cancel", request == null ? Map.of() : request, AgentOsOperationResponse.class
        ));
    }

    @DeleteMapping("/runs/{runId}")
    public ResponseEntity<Map<String, Object>> deleteRun(@PathVariable String runId) {
        return AgentOsControllerSupport.response(gateway.delete(AgentOsPaths.run(runId)));
    }
}
