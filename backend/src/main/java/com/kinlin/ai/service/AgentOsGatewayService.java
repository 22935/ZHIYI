package com.kinlin.ai.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.config.AgentProperties;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
public class AgentOsGatewayService {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_BODY =
            new ParameterizedTypeReference<>() {
            };
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    public static final String INTERNAL_HTTP_STATUS_KEY = "_httpStatus";

    private final WebClient webClient;
    private final AgentProperties agentProperties;
    private final int timeoutMs;

    public AgentOsGatewayService(WebClient.Builder webClientBuilder, AgentProperties agentProperties,
                                 @Value("${ai.service.url:http://localhost:8000}") String aiServiceUrl) {
        this.webClient = webClientBuilder.baseUrl(aiServiceUrl).build();
        this.agentProperties = agentProperties;
        this.timeoutMs = agentProperties.getTimeoutMs();
    }

    public Map<String, Object> get(String path) {
        if (!agentProperties.isEnabled()) {
            return disabledResponse(path);
        }
        try {
            return webClient.get()
                    .uri(path)
                    .retrieve()
                    .bodyToMono(MAP_BODY)
                    .timeout(Duration.ofMillis(timeoutMs))
                    .onErrorResume(e -> toErrorResponse(e, path))
                    .block();
        } catch (Exception e) {
            return errorResponse(e, path);
        }
    }

    public Map<String, Object> post(String path, Object body) {
        if (!agentProperties.isEnabled()) {
            return disabledResponse(path);
        }
        try {
            return webClient.post()
                    .uri(path)
                    .bodyValue(body != null ? body : new HashMap<>())
                    .retrieve()
                    .bodyToMono(MAP_BODY)
                    .timeout(Duration.ofMillis(timeoutMs))
                    .onErrorResume(e -> toErrorResponse(e, path))
                    .block();
        } catch (Exception e) {
            return errorResponse(e, path);
        }
    }

    public String getText(String path) {
        if (!agentProperties.isEnabled()) {
            return "AgentOS gateway is disabled by configuration. path=" + path;
        }
        try {
            return webClient.get()
                    .uri(path)
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMillis(timeoutMs))
                    .onErrorResume(e -> Mono.just(errorText(e, path)))
                    .block();
        } catch (Exception e) {
            return errorText(e, path);
        }
    }

    private Mono<Map<String, Object>> toErrorResponse(Throwable throwable, String path) {
        Exception ex = throwable instanceof Exception ? (Exception) throwable : new Exception(throwable.getMessage(), throwable);
        return Mono.just(errorResponse(ex, path));
    }

    private Map<String, Object> disabledResponse(String path) {
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", "AgentOS gateway is disabled by configuration.");
        response.put("error", "agent.disabled");
        response.put("path", path);
        response.put(INTERNAL_HTTP_STATUS_KEY, HttpStatus.SERVICE_UNAVAILABLE.value());
        return response;
    }

    private Map<String, Object> errorResponse(Exception e, String path) {
        log.error("AgentOS gateway request failed. path={}", path, e);
        if (e instanceof WebClientResponseException webClientError) {
            return upstreamErrorResponse(webClientError, path);
        }
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", "AgentOS gateway unavailable.");
        response.put("error", e.getClass().getSimpleName());
        response.put("path", path);
        response.put(INTERNAL_HTTP_STATUS_KEY, HttpStatus.SERVICE_UNAVAILABLE.value());
        return response;
    }

    private Map<String, Object> upstreamErrorResponse(WebClientResponseException e, String path) {
        Map<String, Object> response = parseJsonObject(e.getResponseBodyAsString());
        int upstreamStatus = e.getStatusCode().value();
        int gatewayStatus = e.getStatusCode().is4xxClientError()
                ? upstreamStatus
                : HttpStatus.BAD_GATEWAY.value();
        response.putIfAbsent("success", false);
        response.putIfAbsent("message", e.getMessage() == null ? "AgentOS upstream request failed." : e.getStatusText());
        response.putIfAbsent("error", e.getClass().getSimpleName());
        response.put("path", path);
        response.put("upstreamStatus", upstreamStatus);
        response.put(INTERNAL_HTTP_STATUS_KEY, gatewayStatus);
        return response;
    }

    private Map<String, Object> parseJsonObject(String text) {
        if (text == null || text.isBlank()) {
            return new HashMap<>();
        }
        try {
            return OBJECT_MAPPER.readValue(text, new TypeReference<>() {
            });
        } catch (Exception ignored) {
            Map<String, Object> response = new HashMap<>();
            response.put("upstreamBody", text);
            return response;
        }
    }

    public ResponseEntity<String> getTextResponse(String path) {
        if (!agentProperties.isEnabled()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("AgentOS gateway is disabled by configuration. path=" + path);
        }
        try {
            return webClient.get()
                    .uri(path)
                    .retrieve()
                    .toEntity(String.class)
                    .timeout(Duration.ofMillis(timeoutMs))
                    .onErrorResume(e -> Mono.just(errorTextResponse(e, path)))
                    .block();
        } catch (Exception e) {
            return errorTextResponse(e, path);
        }
    }

    private String errorText(Throwable e, String path) {
        return errorTextResponse(e, path).getBody();
    }

    private ResponseEntity<String> errorTextResponse(Throwable e, String path) {
        log.error("AgentOS gateway text request failed. path={}", path, e);
        if (e instanceof WebClientResponseException webClientError) {
            int status = webClientError.getStatusCode().is4xxClientError()
                    ? webClientError.getStatusCode().value()
                    : HttpStatus.BAD_GATEWAY.value();
            String message = webClientError.getResponseBodyAsString();
            if (message == null || message.isBlank()) {
                message = webClientError.getStatusText();
            }
            return ResponseEntity.status(status).body(message);
        }
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("AgentOS gateway request failed: AgentOS gateway unavailable.\npath=" + path + "\n");
    }
}
