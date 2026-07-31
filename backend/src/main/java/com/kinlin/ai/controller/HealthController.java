package com.kinlin.ai.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

/**
 * 健康检查控制器
 */
@RestController
@RequestMapping("/health")
public class HealthController {

    private final JdbcTemplate jdbcTemplate;
    private final RedisConnectionFactory redisConnectionFactory;
    private final WebClient.Builder webClientBuilder;

    @Value("${ai.service.url:http://localhost:8000}")
    private String aiServiceUrl;

    public HealthController(JdbcTemplate jdbcTemplate, RedisConnectionFactory redisConnectionFactory, WebClient.Builder webClientBuilder) {
        this.jdbcTemplate = jdbcTemplate;
        this.redisConnectionFactory = redisConnectionFactory;
        this.webClientBuilder = webClientBuilder;
    }

    @GetMapping
    public ResponseEntity<Map<String, Object>> health() {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "UP");
        response.put("service", "federal-hub-backend");
        response.put("version", "1.0.0");
        return ResponseEntity.ok(response);
    }

    @GetMapping("/live")
    public ResponseEntity<Map<String, Object>> live() {
        return ResponseEntity.ok(Map.of("status", "UP", "service", "kinlin-backend", "check", "liveness"));
    }

    @GetMapping("/ready")
    public ResponseEntity<Map<String, Object>> ready() {
        Map<String, Object> checks = new HashMap<>();
        try {
            checks.put("postgres", jdbcTemplate.queryForObject("SELECT 1", Integer.class) != null);
            try (RedisConnection connection = redisConnectionFactory.getConnection()) {
                String pong = connection.ping();
                checks.put("redis", "PONG".equalsIgnoreCase(pong));
            }
            return ResponseEntity.ok(Map.of("status", "UP", "checks", checks));
        } catch (Exception e) {
            checks.put("error", e.getClass().getSimpleName());
            return ResponseEntity.status(503).body(Map.of("status", "DOWN", "checks", checks));
        }
    }

    @GetMapping("/dependencies")
    public ResponseEntity<Map<String, Object>> dependencies() {
        Map<String, Object> ai = new HashMap<>();
        try {
            Object body = webClientBuilder.baseUrl(aiServiceUrl).build().get().uri("/health/dependencies")
                    .retrieve().bodyToMono(Object.class).block(java.time.Duration.ofSeconds(3));
            ai.put("status", "REACHABLE");
            ai.put("detail", body);
        } catch (Exception e) {
            ai.put("status", "DEGRADED");
            ai.put("error", e.getClass().getSimpleName());
        }
        ai.put("affectsReadiness", false);
        return ResponseEntity.ok(Map.of("status", ai.get("status"), "dependencies", Map.of("aiService", ai)));
    }
}

