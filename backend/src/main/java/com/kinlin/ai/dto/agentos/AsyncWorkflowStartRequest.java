package com.kinlin.ai.dto.agentos;

import java.util.List;
import java.util.Map;

/** Request accepted by the asynchronous workflow preparation endpoint. */
public record AsyncWorkflowStartRequest(
        String title,
        String domain,
        String intent,
        String roleType,
        String taskType,
        Map<String, Object> input,
        String securityLevel,
        String priority,
        String workflowId,
        String reviewMode,
        String clientRequestId,
        String planningDiversity,
        Long planningSeed,
        List<String> enabledPluginIds
) {
    public AsyncWorkflowStartRequest {
        domain = domain == null ? "general" : domain;
        intent = intent == null ? "general" : intent;
        input = input == null ? Map.of() : input;
        securityLevel = securityLevel == null ? "internal" : securityLevel;
        priority = priority == null ? "normal" : priority;
        reviewMode = reviewMode == null ? "auto" : reviewMode;
        planningDiversity = planningDiversity == null ? "stable" : planningDiversity;
    }
}
