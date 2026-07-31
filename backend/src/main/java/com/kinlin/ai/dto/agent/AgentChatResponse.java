package com.kinlin.ai.dto.agent;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Data;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Shared agent chat response DTO.
 */
@Data
@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonIgnoreProperties(ignoreUnknown = true)
public class AgentChatResponse {

    private boolean success;

    private String answer;

    @JsonAlias("session_id")
    private String sessionId;

    @JsonAlias("skills_used")
    private List<String> skillsUsed = new ArrayList<>();

    private List<Map<String, Object>> trace = new ArrayList<>();

    private Map<String, Object> routing;

    @JsonAlias("workflow_run_id")
    private String workflowRunId;

    @JsonAlias("workflow_id")
    private String workflowId;

    @JsonAlias("workflow_status")
    private String workflowStatus;

    @JsonAlias("runtime_engine")
    private String runtimeEngine;

    @JsonAlias("implementation_id")
    private String implementationId;

    @JsonAlias("risk_level")
    private String riskLevel;

    private Map<String, Object> federated;

    @JsonAlias("evidence_analysis")
    private Map<String, Object> evidenceAnalysis;

    @JsonAlias("limitation_calculation")
    private Map<String, Object> limitationCalc;

    @JsonAlias("jurisdiction_determination")
    private Map<String, Object> jurisdiction;

    @JsonAlias("hearing_outline_generation")
    private Map<String, Object> hearingOutline;

    @JsonAlias("student_diagnosis")
    private Map<String, Object> studentDiagnosis;

    @JsonAlias("lesson_plan_generation")
    private Map<String, Object> lessonPlan;

    @JsonAlias("homework_grading")
    private Map<String, Object> homeworkGrading;

    @JsonAlias("error_analysis_question_push")
    private Map<String, Object> errorQuestionPush;

    @JsonAlias("inspiration_expand")
    private Map<String, Object> inspirationExpand;

    @JsonAlias("outline_generate")
    private Map<String, Object> outlineGenerate;

    @JsonAlias("content_write")
    private Map<String, Object> contentWrite;

    @JsonAlias("character_relation_map")
    private Map<String, Object> characterRelationMap;

    @JsonAlias("requirement_analysis")
    private Map<String, Object> requirementAnalysis;

    @JsonAlias("codebase_semantic_search")
    private Map<String, Object> codebaseSemanticSearch;

    @JsonAlias("code_generation")
    private Map<String, Object> codeGeneration;

    @JsonAlias("diagram_generation")
    private Map<String, Object> diagramGeneration;

    private String message;

    private String error;

    public static AgentChatResponse failure(String sessionId, String message, String error) {
        AgentChatResponse response = new AgentChatResponse();
        response.setSuccess(false);
        response.setAnswer("Sorry, the agent is temporarily unavailable. Please try again later.");
        response.setSessionId(sessionId);
        response.setFederated(new java.util.HashMap<>());
        response.setMessage(message);
        response.setError(error);
        return response;
    }
}
