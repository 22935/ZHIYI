package com.kinlin.ai.service;

import com.kinlin.ai.config.AgentProperties;
import com.kinlin.ai.dto.agent.AgentChatRequest;
import com.kinlin.ai.dto.agent.AgentChatResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;

/**
 * Gateway for forwarding lawyer-agent requests to Python service.
 */
@Slf4j
@Service
public class AgentGatewayService {

    private final AgentProperties agentProperties;
    private final RestTemplate restTemplate;

    public AgentGatewayService(RestTemplateBuilder restTemplateBuilder, AgentProperties agentProperties) {
        this.agentProperties = agentProperties;
        this.restTemplate = restTemplateBuilder
                .setConnectTimeout(Duration.ofMillis(agentProperties.getTimeoutMs()))
                .setReadTimeout(Duration.ofMillis(agentProperties.getTimeoutMs()))
                .build();
    }

    public AgentChatResponse chatWithLawyerAgent(AgentChatRequest request) {
        return chatWithAgent(
                request,
                agentProperties.getPython().getLawyerChatUrl(),
                "lawyer"
        );
    }

    public AgentChatResponse chatWithTeacherAgent(AgentChatRequest request) {
        return chatWithAgent(
                request,
                agentProperties.getPython().getTeacherChatUrl(),
                "teacher"
        );
    }

    public AgentChatResponse chatWithProgrammerAgent(AgentChatRequest request) {
        return chatWithAgent(
                request,
                agentProperties.getPython().getProgrammerChatUrl(),
                "programmer"
        );
    }

    public AgentChatResponse chatWithWriterAgent(AgentChatRequest request) {
        return chatWithAgent(
                request,
                agentProperties.getPython().getWriterChatUrl(),
                "writer"
        );
    }

    private AgentChatResponse chatWithAgent(AgentChatRequest request, String endpointUrl, String roleLabel) {
        if (!agentProperties.isEnabled()) {
            return AgentChatResponse.failure(
                    request.getSessionId(),
                    "Agent service is disabled by configuration.",
                    "agent.disabled"
            );
        }

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<AgentChatRequest> httpEntity = new HttpEntity<>(request, headers);

            ResponseEntity<AgentChatResponse> response = restTemplate.postForEntity(
                    endpointUrl,
                    httpEntity,
                    AgentChatResponse.class
            );

            if (response.getBody() == null) {
                return AgentChatResponse.failure(
                        request.getSessionId(),
                        "Python agent returned empty response.",
                        "agent.empty_response"
                );
            }

            AgentChatResponse body = response.getBody();
            if (body.getSessionId() == null || body.getSessionId().isBlank()) {
                body.setSessionId(request.getSessionId());
            }
            return body;
        } catch (ResourceAccessException e) {
            log.error("Python agent access timeout/error", e);
            return AgentChatResponse.failure(
                    request.getSessionId(),
                    "Python agent timeout or unreachable. Please try again later.",
                    e.getMessage()
            );
        } catch (HttpStatusCodeException e) {
            log.error("Python agent HTTP error: {}", e.getStatusCode(), e);
            return AgentChatResponse.failure(
                    request.getSessionId(),
                    "Python agent returned an error status.",
                    e.getResponseBodyAsString()
            );
        } catch (Exception e) {
            log.error("Unexpected agent gateway error", e);
            return AgentChatResponse.failure(
                    request.getSessionId(),
                    "Unexpected error while calling " + roleLabel + " agent.",
                    e.getMessage()
            );
        }
    }
}
