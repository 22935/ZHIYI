package com.kinlin.ai.dto.agent;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Data;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Lawyer agent chat response DTO.
 */
@Data
@JsonInclude(JsonInclude.Include.NON_NULL)
public class AgentChatResponse {

    private boolean success;

    private String answer;

    @JsonAlias("session_id")
    private String sessionId;

    @JsonAlias("skills_used")
    private List<String> skillsUsed = new ArrayList<>();

    private List<Map<String, Object>> trace = new ArrayList<>();

    @JsonAlias("risk_level")
    private String riskLevel;

    private Map<String, Object> federated;

    private String message;

    private String error;

    public static AgentChatResponse failure(String sessionId, String message, String error) {
        AgentChatResponse response = new AgentChatResponse();
        response.setSuccess(false);
        response.setAnswer("抱歉，律师智能体当前不可用，请稍后重试。");
        response.setSessionId(sessionId);
        response.setFederated(new java.util.HashMap<>());
        response.setMessage(message);
        response.setError(error);
        return response;
    }
}
