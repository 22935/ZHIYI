package com.kinlin.ai.controller;

import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

/**
 * Proxies /ai requests from backend to Python AI service.
 */
@Slf4j
@RestController
@RequestMapping("/ai")
@RequiredArgsConstructor
public class AiServiceProxyController {

    private static final MediaType JSON_UTF8 = MediaType.parseMediaType("application/json;charset=UTF-8");

    private final WebClient.Builder webClientBuilder;

    @Value("${ai.service.url}")
    private String aiServiceUrl;

    @Value("${ai.service.timeout}")
    private int timeout;

    private WebClient getWebClient() {
        return webClientBuilder
                .baseUrl(aiServiceUrl)
                .build();
    }

    @GetMapping("/**")
    public ResponseEntity<?> proxyGet(HttpServletRequest request) {
        try {
            String requestURI = request.getRequestURI();
            String path = extractPath(request);
            log.info("Proxy GET request: requestURI={}, extractedPath={}", requestURI, path);

            if (isImageRequest(path)) {
                byte[] imageData = getWebClient().get()
                        .uri(path)
                        .retrieve()
                        .bodyToMono(byte[].class)
                        .timeout(Duration.ofMillis(timeout))
                        .onErrorResume(e -> {
                            log.warn("Proxy image request failed: {} - {}", path, e.getMessage());
                            return Mono.empty();
                        })
                        .block();

                if (imageData != null && imageData.length > 0) {
                    return ResponseEntity.ok()
                            .header("Content-Type", resolveImageContentType(path))
                            .header("Cache-Control", "public, max-age=31536000")
                            .header("Access-Control-Allow-Origin", "*")
                            .body(imageData);
                }

                return ResponseEntity.status(404)
                        .contentType(JSON_UTF8)
                        .body(createErrorResponse(new RuntimeException("Image file not found or inaccessible"), path));
            }

            Object response = getWebClient().get()
                    .uri(path)
                    .retrieve()
                    .bodyToMono(Object.class)
                    .timeout(Duration.ofMillis(timeout))
                    .onErrorResume(e -> {
                        log.warn("Proxy GET request failed: {} - {}", path, e.getMessage());
                        Exception ex = e instanceof Exception ? (Exception) e : new Exception(e.getMessage(), e);
                        return Mono.just(createErrorResponse(ex, path));
                    })
                    .block();

            return ResponseEntity.ok()
                    .contentType(JSON_UTF8)
                    .body(response);
        } catch (Exception e) {
            log.error("Proxy GET request failed", e);
            return ResponseEntity.status(500)
                    .contentType(JSON_UTF8)
                    .body(createErrorResponse(e, ""));
        }
    }

    @PostMapping("/**")
    public ResponseEntity<Object> proxyPost(
            @RequestBody(required = false) Object body,
            HttpServletRequest request
    ) {
        try {
            String path = extractPath(request);
            log.debug("Proxy POST request to Python service: {}", path);

            Object response = getWebClient().post()
                    .uri(path)
                    .bodyValue(body != null ? body : new HashMap<>())
                    .retrieve()
                    .bodyToMono(Object.class)
                    .timeout(Duration.ofMillis(timeout))
                    .onErrorResume(e -> {
                        log.warn("Proxy POST request failed: {} - {}", path, e.getMessage());
                        Exception ex = e instanceof Exception ? (Exception) e : new Exception(e.getMessage(), e);
                        return Mono.just(createErrorResponse(ex, path));
                    })
                    .block();

            return ResponseEntity.ok()
                    .contentType(JSON_UTF8)
                    .body(response);
        } catch (Exception e) {
            log.error("Proxy POST request failed", e);
            return ResponseEntity.status(500)
                    .contentType(JSON_UTF8)
                    .body(createErrorResponse(e, ""));
        }
    }

    private boolean isImageRequest(String path) {
        return path.contains("/digital-human/image/")
                || path.endsWith(".png")
                || path.endsWith(".jpg")
                || path.endsWith(".jpeg")
                || path.endsWith(".gif")
                || path.endsWith(".webp");
    }

    private String resolveImageContentType(String path) {
        if (path.endsWith(".jpg") || path.endsWith(".jpeg")) {
            return "image/jpeg";
        }
        if (path.endsWith(".gif")) {
            return "image/gif";
        }
        if (path.endsWith(".webp")) {
            return "image/webp";
        }
        return "image/png";
    }

    /**
     * Preserve /ai prefix because Python service routes are also rooted at /ai.
     */
    private String extractPath(HttpServletRequest request) {
        String requestURI = request.getRequestURI();
        String contextPath = request.getContextPath();

        log.debug("Extracting path: requestURI={}, contextPath={}", requestURI, contextPath);

        String path = requestURI;
        if (contextPath != null && !contextPath.isEmpty()) {
            path = path.substring(contextPath.length());
        }

        String queryString = request.getQueryString();
        if (queryString != null && !queryString.isEmpty()) {
            path += "?" + queryString;
        }

        log.debug("Forwarding path to Python service: {}", path);
        return path;
    }

    private Map<String, Object> createErrorResponse(Exception e, String path) {
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);

        String errorMessage = e.getMessage();
        if (errorMessage == null || errorMessage.isEmpty()) {
            errorMessage = "Python AI service is unavailable.";
        }

        if (errorMessage.contains("Connection refused") || errorMessage.contains("timeout")) {
            response.put("message", "Python AI service is unavailable. Please ensure service is running at " + aiServiceUrl);
        } else {
            response.put("message", "Request failed: " + errorMessage);
        }

        response.put("error", e.getClass().getSimpleName());
        response.put("path", path);
        return response;
    }
}