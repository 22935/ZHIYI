package com.kinlin.ai.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.kinlin.ai.config.AgentProperties;
import com.kinlin.ai.dto.agentos.WorkflowProgressResponse;
import com.kinlin.ai.dto.agentos.AsyncWorkflowStartResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.stereotype.Service;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.BodyInserters;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

/** AgentOS 网关服务 — 通过 WebClient 将请求代理转发到 Python AgentOS 后端 */
@Slf4j
@Service
public class AgentOsGatewayService {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_BODY =
            new ParameterizedTypeReference<>() {
            };
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper()
            .findAndRegisterModules()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
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
        return get(path, timeoutMs);
    }

    public Map<String, Object> getProgress(String path) {
        return get(path, agentProperties.getProgressTimeoutMs());
    }

    private Map<String, Object> get(String path, int requestTimeoutMs) {
        if (!agentProperties.isEnabled()) {
            return disabledResponse(path);
        }
        try {
            return webClient.get()
                    .uri(path)
                    .retrieve()
                    .bodyToMono(MAP_BODY)
                    .timeout(Duration.ofMillis(requestTimeoutMs))
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
        response.put(INTERNAL_HTTP_STATUS_KEY, HttpStatus.SERVICE_UNAVAILABLE.value());
        return response;
    }

    private Map<String, Object> errorResponse(Exception e, String path) {
        log.error("AgentOS gateway request failed. path={}, type={}", path, e.getClass().getSimpleName());
        if (e instanceof WebClientResponseException webClientError) {
            return upstreamErrorResponse(webClientError, path);
        }
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", "AgentOS gateway unavailable.");
        response.put("error", "AGENTOS_UPSTREAM_UNAVAILABLE");
        response.put(INTERNAL_HTTP_STATUS_KEY, HttpStatus.SERVICE_UNAVAILABLE.value());
        return response;
    }

    private Map<String, Object> upstreamErrorResponse(WebClientResponseException e, String path) {
        int upstreamStatus = e.getStatusCode().value();
        int gatewayStatus = e.getStatusCode().is4xxClientError()
                ? upstreamStatus
                : HttpStatus.BAD_GATEWAY.value();
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", e.getStatusCode().is4xxClientError()
                ? safeUpstreamMessage(e.getResponseBodyAsString(), upstreamStatus)
                : "AgentOS service returned an error");
        response.put("error", e.getStatusCode().is4xxClientError()
                ? "AGENTOS_UPSTREAM_CLIENT_ERROR"
                : "AGENTOS_UPSTREAM_ERROR");
        response.put("upstreamStatus", upstreamStatus);
        response.put(INTERNAL_HTTP_STATUS_KEY, gatewayStatus);
        return response;
    }

    /** Rebuild multipart bodies after servlet parsing so the upstream always receives a real file part. */
    public Map<String, Object> postMaterial(String path, MultipartFile file) {
        if (!agentProperties.isEnabled()) {
            return disabledResponse(path);
        }
        try {
            MultipartBodyBuilder parts = new MultipartBodyBuilder();
            ByteArrayResource resource = new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() {
                    return file.getOriginalFilename() == null ? "upload" : file.getOriginalFilename();
                }
            };
            MediaType partType;
            try {
                partType = file.getContentType() == null
                        ? MediaType.APPLICATION_OCTET_STREAM
                        : MediaType.parseMediaType(file.getContentType());
            } catch (IllegalArgumentException ignored) {
                partType = MediaType.APPLICATION_OCTET_STREAM;
            }
            parts.part("file", resource).filename(resource.getFilename()).contentType(partType);
            return webClient.post()
                    .uri(path)
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(BodyInserters.fromMultipartData(parts.build()))
                    .exchangeToMono(response -> response.bodyToMono(MAP_BODY)
                            .defaultIfEmpty(new HashMap<>())
                            .map(payload -> withHttpStatus(payload, response.statusCode().value())))
                    .timeout(Duration.ofMillis(timeoutMs))
                    .onErrorResume(e -> toErrorResponse(e, path))
                    .block();
        } catch (Exception e) {
            return errorResponse(e, path);
        }
    }

    public Map<String, Object> delete(String path) {
        if (!agentProperties.isEnabled()) {
            return disabledResponse(path);
        }
        try {
            return webClient.delete()
                    .uri(path)
                    .exchangeToMono(response -> response.bodyToMono(MAP_BODY)
                            .defaultIfEmpty(new HashMap<>())
                            .map(payload -> withHttpStatus(payload, response.statusCode().value())))
                    .timeout(Duration.ofMillis(timeoutMs))
                    .onErrorResume(e -> toErrorResponse(e, path))
                    .block();
        } catch (Exception e) {
            return errorResponse(e, path);
        }
    }

    /** Preserve upstream status for the fast asynchronous workflow preparation call. */
    public Map<String, Object> postAsyncStart(String path, Object body) {
        if (!agentProperties.isEnabled()) {
            return disabledResponse(path);
        }
        try {
            return webClient.post()
                    .uri(path)
                    .bodyValue(body != null ? body : new HashMap<>())
                    .exchangeToMono(response -> response.bodyToMono(MAP_BODY)
                            .defaultIfEmpty(new HashMap<>())
                            .map(payload -> withHttpStatus(payload, response.statusCode().value())))
                    .timeout(Duration.ofMillis(agentProperties.getAsyncStartTimeoutMs()))
                    .onErrorResume(e -> toErrorResponse(e, path))
                    .block();
        } catch (Exception e) {
            return errorResponse(e, path);
        }
    }

    public WorkflowProgressResponse parseWorkflowProgress(Map<String, Object> body) {
        try {
            return OBJECT_MAPPER.convertValue(body, WorkflowProgressResponse.class);
        } catch (IllegalArgumentException exception) {
            log.warn("AgentOS progress response validation failed. type={}",
                    exception.getClass().getSimpleName());
            throw new IllegalStateException("AgentOS returned an invalid progress response", exception);
        }
    }

    public AsyncWorkflowStartResponse parseAsyncWorkflowStart(Map<String, Object> body) {
        try {
            return OBJECT_MAPPER.convertValue(body, AsyncWorkflowStartResponse.class);
        } catch (IllegalArgumentException exception) {
            log.warn("AgentOS async start response validation failed. type={}",
                    exception.getClass().getSimpleName());
            throw new IllegalStateException("AgentOS returned an invalid async start response", exception);
        }
    }

    private Map<String, Object> withHttpStatus(Map<String, Object> payload, int status) {
        Map<String, Object> response = new HashMap<>(payload == null ? Map.of() : payload);
        response.put(INTERNAL_HTTP_STATUS_KEY, status);
        return response;
    }

    private String safeUpstreamMessage(String body, int status) {
        Map<String, Object> parsed = parseJsonObject(body);
        for (String key : java.util.List.of("message", "detail", "error")) {
            Object value = parsed.get(key);
            if (value instanceof String text && !text.isBlank()) {
                String sanitized = text.replaceAll("[\\r\\n\\t]", " ").trim();
                return sanitized.substring(0, Math.min(sanitized.length(), 300));
            }
        }
        return "AgentOS request was rejected (HTTP " + status + ")";
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
        log.error("AgentOS gateway text request failed. path={}, type={}", path, e.getClass().getSimpleName());
        if (e instanceof WebClientResponseException webClientError) {
            int status = webClientError.getStatusCode().is4xxClientError()
                    ? webClientError.getStatusCode().value()
                    : HttpStatus.BAD_GATEWAY.value();
            String message = webClientError.getStatusCode().is4xxClientError()
                    ? safeUpstreamMessage(webClientError.getResponseBodyAsString(), webClientError.getStatusCode().value())
                    : "AgentOS service returned an error";
            return ResponseEntity.status(status).body(message);
        }
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("AgentOS gateway unavailable.");
    }
}
