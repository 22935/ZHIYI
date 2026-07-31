package com.kinlin.ai.gateway;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import com.kinlin.ai.security.AuthenticatedUserContext;
import reactor.core.publisher.Flux;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AiSseGatewayServiceTest {

    private HttpServer server;
    private String baseUrl;

    @BeforeEach
    void startServer() throws IOException {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        new AuthenticatedUserContext(UUID.randomUUID(), "sse-test", "USER", null, null),
                        null,
                        java.util.List.of()
                )
        );
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(Executors.newCachedThreadPool());
        server.createContext("/ai/events", exchange -> stream(exchange, List.of(
                ": heartbeat\n\n",
                "data: {\"delta\":\"hello\"}\n\n",
                "data: [DONE]\n\n"
        ), 5));
        server.createContext("/ai/idle", exchange -> stream(exchange, List.of(
                "data: [DONE]\n\n"
        ), 180));
        server.createContext("/ai/long", exchange -> stream(exchange, List.of(
                ": heartbeat\n\n", ": heartbeat\n\n", ": heartbeat\n\n",
                ": heartbeat\n\n", "data: [DONE]\n\n"
        ), 25));
        server.createContext("/ai/rejected", exchange -> respond(exchange, 422));
        server.createContext("/ai/failure", exchange -> respond(exchange, 500));
        server.start();
        baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
        SecurityContextHolder.clearContext();
    }

    @Test
    void preservesCommentsDataAndDoneWithoutBuffering() {
        ResponseEntity<Flux<ServerSentEvent<String>>> response = service(200, 1_000)
                .openPost("/ai/events", java.util.Map.of()).block(Duration.ofSeconds(1));
        List<ServerSentEvent<String>> events = response.getBody().collectList().block(Duration.ofSeconds(1));

        assertEquals(200, response.getStatusCode().value());
        assertEquals("heartbeat", events.get(0).comment());
        assertEquals("{\"delta\":\"hello\"}", events.get(1).data());
        assertEquals("[DONE]", events.get(2).data());
    }

    @Test
    void idleTimeoutResetsOnEventsAndIsDistinctFromMaximumDuration() {
        ResponseEntity<Flux<ServerSentEvent<String>>> idle = service(40, 1_000)
                .openPost("/ai/idle", java.util.Map.of()).block(Duration.ofSeconds(1));
        List<ServerSentEvent<String>> idleEvents = idle.getBody().collectList().block(Duration.ofSeconds(1));

        ResponseEntity<Flux<ServerSentEvent<String>>> maximum = service(80, 70)
                .openPost("/ai/long", java.util.Map.of()).block(Duration.ofSeconds(1));
        List<ServerSentEvent<String>> maximumEvents = maximum.getBody().collectList().block(Duration.ofSeconds(1));

        assertTrue(idleEvents.stream().anyMatch(event -> event.data() != null
                && event.data().contains("SSE_IDLE_TIMEOUT")));
        assertTrue(maximumEvents.stream().anyMatch(event -> event.data() != null
                && event.data().contains("SSE_MAX_DURATION")));
        assertTrue(maximumEvents.stream().filter(event -> "heartbeat".equals(event.comment())).count() >= 2);
    }

    @Test
    void mapsPreStreamUpstreamErrorsBeforeResponseStarts() {
        ResponseEntity<Flux<ServerSentEvent<String>>> rejected = service(100, 1_000)
                .openPost("/ai/rejected", java.util.Map.of()).block(Duration.ofSeconds(1));
        ResponseEntity<Flux<ServerSentEvent<String>>> failure = service(100, 1_000)
                .openPost("/ai/failure", java.util.Map.of()).block(Duration.ofSeconds(1));

        assertEquals(422, rejected.getStatusCode().value());
        assertEquals(502, failure.getStatusCode().value());
        assertTrue(failure.getBody().blockFirst().data().contains("AI_STREAM_UPSTREAM_ERROR"));
    }

    private AiSseGatewayService service(long idleMs, long maximumMs) {
        return new AiSseGatewayService(WebClient.builder(), baseUrl, idleMs, maximumMs);
    }

    private void stream(HttpExchange exchange, List<String> events, long delayMs) throws IOException {
        exchange.getRequestBody().readAllBytes();
        exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
        exchange.sendResponseHeaders(200, 0);
        try {
            for (String event : events) {
                try {
                    Thread.sleep(delayMs);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    break;
                }
                exchange.getResponseBody().write(event.getBytes(StandardCharsets.UTF_8));
                exchange.getResponseBody().flush();
            }
        } finally {
            exchange.close();
        }
    }

    private void respond(HttpExchange exchange, int status) throws IOException {
        exchange.getRequestBody().readAllBytes();
        exchange.sendResponseHeaders(status, -1);
        exchange.close();
    }
}
