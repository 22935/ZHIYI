package com.kinlin.ai.gateway;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.Exceptions;
import com.kinlin.ai.observability.TraceContext;

import java.io.IOException;
import java.net.ConnectException;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeoutException;

/** Fixed-upstream, header-whitelisted proxy for non-streaming Python AI routes. */
@Slf4j
@Service
public class AiProxyService {

    private static final Set<String> REQUEST_HEADER_ALLOWLIST = Set.of(
            HttpHeaders.CONTENT_TYPE.toLowerCase(Locale.ROOT),
            HttpHeaders.ACCEPT.toLowerCase(Locale.ROOT),
            HttpHeaders.ACCEPT_LANGUAGE.toLowerCase(Locale.ROOT),
            HttpHeaders.USER_AGENT.toLowerCase(Locale.ROOT)
    );
    private static final Set<String> RESPONSE_HEADER_ALLOWLIST = Set.of(
            HttpHeaders.CONTENT_TYPE.toLowerCase(Locale.ROOT),
            HttpHeaders.CONTENT_DISPOSITION.toLowerCase(Locale.ROOT),
            HttpHeaders.CACHE_CONTROL.toLowerCase(Locale.ROOT)
    );

    private final WebClient webClient;
    private final ObjectMapper objectMapper;
    private final Duration timeout;

    public AiProxyService(
            WebClient.Builder webClientBuilder,
            ObjectMapper objectMapper,
            @Value("${ai.service.url:http://localhost:8000}") String aiServiceUrl,
            @Value("${ai.service.timeout:240000}") int timeoutMs
    ) {
        this.webClient = webClientBuilder.baseUrl(aiServiceUrl).build();
        this.objectMapper = objectMapper;
        this.timeout = Duration.ofMillis(timeoutMs);
    }

    public ResponseEntity<byte[]> forward(HttpServletRequest request) throws IOException {
        HttpMethod method = HttpMethod.valueOf(request.getMethod());
        String path = safeUpstreamPath(request);
        byte[] requestBody = request.getInputStream().readAllBytes();

        try {
            WebClient.RequestBodySpec requestSpec = webClient.method(method)
                    .uri(path)
                    .headers(headers -> copyAllowedRequestHeaders(request, headers));
            WebClient.RequestHeadersSpec<?> outgoing = requestBody.length == 0
                    ? requestSpec
                    : requestSpec.bodyValue(requestBody);

            ResponseEntity<byte[]> response = outgoing.exchangeToMono(upstream ->
                            upstream.bodyToMono(byte[].class)
                                    .defaultIfEmpty(new byte[0])
                                    .map(body -> mapResponse(upstream.statusCode().value(), upstream.headers().asHttpHeaders(), body))
                    )
                    .timeout(timeout)
                    .block();
            return response == null ? gatewayError(HttpStatus.BAD_GATEWAY, "AI_UPSTREAM_INVALID_RESPONSE") : response;
        } catch (Exception error) {
            Throwable cause = Exceptions.unwrap(error);
            if (isConnectionFailure(cause)) {
                log.warn("AI upstream connection unavailable. method={}, path={}, type={}",
                        method, request.getRequestURI(), cause.getClass().getSimpleName());
                return gatewayError(HttpStatus.SERVICE_UNAVAILABLE, "AI_UPSTREAM_UNAVAILABLE");
            }
            if (isTimeout(cause)) {
                log.warn("AI upstream read timeout. method={}, path={}", method, request.getRequestURI());
                return gatewayError(HttpStatus.GATEWAY_TIMEOUT, "AI_UPSTREAM_TIMEOUT");
            }
            log.error("AI upstream invalid response. method={}, path={}, type={}",
                    method, request.getRequestURI(), cause.getClass().getSimpleName());
            return gatewayError(HttpStatus.BAD_GATEWAY, "AI_UPSTREAM_INVALID_RESPONSE");
        }
    }

    private ResponseEntity<byte[]> mapResponse(int status, HttpHeaders upstreamHeaders, byte[] body) {
        if (status >= 200 && status < 300) {
            HttpHeaders safeHeaders = new HttpHeaders();
            upstreamHeaders.forEach((name, values) -> {
                if (RESPONSE_HEADER_ALLOWLIST.contains(name.toLowerCase(Locale.ROOT))) {
                    safeHeaders.put(name, List.copyOf(values));
                }
            });
            return new ResponseEntity<>(body, safeHeaders, status);
        }
        if (status >= 400 && status < 500) {
            return jsonResponse(HttpStatus.valueOf(status), Map.of(
                    "error", "AI_UPSTREAM_CLIENT_ERROR",
                    "message", safeClientMessage(body, status),
                    "upstreamStatus", status,
                    "traceId", TraceContext.currentTraceId()
            ));
        }
        log.warn("AI upstream server error. upstreamStatus={}", status);
        return jsonResponse(HttpStatus.BAD_GATEWAY, Map.of(
                "error", "AI_UPSTREAM_ERROR",
                "message", "AI service returned an error",
                "upstreamStatus", status,
                "traceId", TraceContext.currentTraceId()
        ));
    }

    private String safeClientMessage(byte[] body, int status) {
        try {
            JsonNode root = objectMapper.readTree(body);
            for (String field : List.of("message", "detail", "error")) {
                JsonNode value = root.get(field);
                if (value != null && value.isTextual() && !value.textValue().isBlank()) {
                    return truncate(value.textValue(), 300);
                }
            }
        } catch (Exception ignored) {
            // Unstructured upstream bodies are intentionally not reflected.
        }
        return "AI request was rejected (HTTP " + status + ")";
    }

    private String safeUpstreamPath(HttpServletRequest request) {
        String path = request.getRequestURI();
        if (path == null || !path.startsWith("/ai/") || path.startsWith("//")
                || path.contains("..") || path.contains("\\") || containsControlCharacter(path)) {
            throw new IllegalArgumentException("invalid AI proxy path");
        }
        String query = request.getQueryString();
        if (query != null && !query.isBlank()) {
            if (containsControlCharacter(query)) {
                throw new IllegalArgumentException("invalid AI proxy query");
            }
            path += "?" + query;
        }
        return path;
    }

    private void copyAllowedRequestHeaders(HttpServletRequest request, HttpHeaders target) {
        request.getHeaderNames().asIterator().forEachRemaining(name -> {
            if (REQUEST_HEADER_ALLOWLIST.contains(name.toLowerCase(Locale.ROOT))) {
                target.put(name, java.util.Collections.list(request.getHeaders(name)));
            }
        });
    }

    private boolean isTimeout(Throwable error) {
        return error instanceof TimeoutException
                || error.getClass().getSimpleName().contains("Timeout");
    }

    private boolean isConnectionFailure(Throwable error) {
        if (error instanceof WebClientRequestException requestError) {
            Throwable cause = requestError.getCause();
            return cause instanceof ConnectException || cause instanceof UnknownHostException
                    || (cause != null && cause.getClass().getSimpleName().contains("Connect"));
        }
        Throwable current = error;
        while (current != null) {
            if (current instanceof ConnectException || current instanceof UnknownHostException
                    || current.getClass().getSimpleName().contains("ConnectException")) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private boolean containsControlCharacter(String value) {
        return value.chars().anyMatch(character -> character < 0x20 || character == 0x7f);
    }

    private String truncate(String value, int maximumLength) {
        String sanitized = value.replaceAll("[\\r\\n\\t]", " ").trim();
        return sanitized.length() <= maximumLength ? sanitized : sanitized.substring(0, maximumLength);
    }

    private ResponseEntity<byte[]> gatewayError(HttpStatus status, String code) {
        return jsonResponse(status, Map.of(
                "error", code,
                "traceId", TraceContext.currentTraceId(),
                "message", switch (code) {
                    case "AI_UPSTREAM_TIMEOUT" -> "AI service response timed out";
                    case "AI_UPSTREAM_UNAVAILABLE" -> "AI service is unavailable";
                    default -> "AI gateway received an invalid response";
                }
        ));
    }

    private ResponseEntity<byte[]> jsonResponse(HttpStatus status, Map<String, Object> payload) {
        try {
            return ResponseEntity.status(status)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(objectMapper.writeValueAsBytes(payload));
        } catch (Exception impossible) {
            return ResponseEntity.status(status)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"error\":\"AI_GATEWAY_ERROR\"}".getBytes(StandardCharsets.UTF_8));
        }
    }
}
