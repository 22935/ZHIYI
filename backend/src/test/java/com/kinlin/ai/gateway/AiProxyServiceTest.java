package com.kinlin.ai.gateway;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.net.ConnectException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AiProxyServiceTest {

    private HttpServer server;
    private String baseUrl;
    private final AtomicReference<com.sun.net.httpserver.Headers> capturedHeaders = new AtomicReference<>();
    private final AtomicReference<byte[]> capturedBody = new AtomicReference<>();

    @BeforeEach
    void startServer() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(Executors.newCachedThreadPool());
        server.createContext("/ai/ok", exchange -> respond(exchange, 200, "{\"ok\":true}"));
        server.createContext("/ai/upload", exchange -> respond(exchange, 200, "{\"uploaded\":true}"));
        server.createContext("/ai/rejected", exchange -> respond(exchange, 422,
                "{\"detail\":\"validation rejected\",\"stack\":\"do-not-leak\"}"));
        server.createContext("/ai/failure", exchange -> respond(exchange, 500,
                "{\"detail\":\"private host and stack\"}"));
        server.createContext("/ai/slow", exchange -> {
            try {
                Thread.sleep(250);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
            respond(exchange, 200, "{\"ok\":true}");
        });
        server.start();
        baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
    }

    @Test
    void passesSuccessAndOnlyAllowlistedClientHeaders() throws Exception {
        MockHttpServletRequest request = request("GET", "/ai/ok");
        request.addHeader("Accept-Language", "zh-CN");
        request.addHeader("Authorization", "Bearer client-jwt");
        request.addHeader("X-User-Id", "forged");

        ResponseEntity<byte[]> response = service(5_000).forward(request);

        assertEquals(200, response.getStatusCode().value());
        assertTrue(new String(response.getBody(), StandardCharsets.UTF_8).contains("true"));
        assertEquals("zh-CN", capturedHeaders.get().getFirst("Accept-Language"));
        assertFalse(capturedHeaders.get().containsKey("Authorization"));
        assertFalse(capturedHeaders.get().containsKey("X-User-Id"));
    }

    @Test
    void preservesSafeClientStatusAndFiltersBody() throws Exception {
        ResponseEntity<byte[]> response = service(5_000).forward(request("POST", "/ai/rejected"));
        String body = new String(response.getBody(), StandardCharsets.UTF_8);

        assertEquals(422, response.getStatusCode().value());
        assertTrue(body.contains("validation rejected"));
        assertFalse(body.contains("do-not-leak"));
    }

    @Test
    void preservesMultipartContentTypeAndRawBody() throws Exception {
        MockHttpServletRequest request = request("POST", "/ai/upload");
        request.setContentType("multipart/form-data; boundary=p2-boundary");
        request.setContent("--p2-boundary\r\nprobe-file\r\n--p2-boundary--\r\n"
                .getBytes(StandardCharsets.UTF_8));

        ResponseEntity<byte[]> response = service(5_000).forward(request);

        assertEquals(200, response.getStatusCode().value());
        assertTrue(capturedHeaders.get().getFirst("Content-Type").startsWith("multipart/form-data"));
        assertTrue(new String(capturedBody.get(), StandardCharsets.UTF_8).contains("probe-file"));
    }

    @Test
    void mapsServerErrorAndReadTimeoutToStableCodes() throws Exception {
        ResponseEntity<byte[]> failure = service(5_000).forward(request("GET", "/ai/failure"));
        ResponseEntity<byte[]> timeout = service(50).forward(request("GET", "/ai/slow"));

        assertEquals(502, failure.getStatusCode().value());
        assertFalse(new String(failure.getBody(), StandardCharsets.UTF_8).contains("private host"));
        assertEquals(504, timeout.getStatusCode().value());
        assertTrue(new String(timeout.getBody(), StandardCharsets.UTF_8).contains("AI_UPSTREAM_TIMEOUT"));
    }

    @Test
    void mapsConnectionFailureAndRejectsUnsafePath() throws Exception {
        AiProxyService unavailable = new AiProxyService(
                WebClient.builder().exchangeFunction(ignored -> Mono.error(new ConnectException("test connection refused"))),
                new ObjectMapper(), "http://127.0.0.1", 1_000
        );
        ResponseEntity<byte[]> response = unavailable.forward(request("GET", "/ai/ok"));

        assertEquals(503, response.getStatusCode().value());
        assertThrows(IllegalArgumentException.class,
                () -> service(5_000).forward(request("GET", "/ai/../admin")));
    }

    private AiProxyService service(int timeoutMs) {
        return new AiProxyService(WebClient.builder(), new ObjectMapper(), baseUrl, timeoutMs);
    }

    private MockHttpServletRequest request(String method, String path) {
        MockHttpServletRequest request = new MockHttpServletRequest(method, path);
        request.setRequestURI(path);
        request.setContentType("application/json");
        if (!"GET".equals(method)) {
            request.setContent("{\"probe\":true}".getBytes(StandardCharsets.UTF_8));
        }
        return request;
    }

    private void respond(HttpExchange exchange, int status, String body) throws java.io.IOException {
        capturedHeaders.set(exchange.getRequestHeaders());
        capturedBody.set(exchange.getRequestBody().readAllBytes());
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }
}
