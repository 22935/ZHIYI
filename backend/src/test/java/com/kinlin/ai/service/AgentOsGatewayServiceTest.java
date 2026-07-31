package com.kinlin.ai.service;

import com.kinlin.ai.config.AgentProperties;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.mock.web.MockMultipartFile;
import reactor.core.publisher.Mono;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AgentOsGatewayServiceTest {

    @Test
    void materialUploadReconstructsMultipartWithFilenameAndBoundary() throws Exception {
        AtomicReference<String> contentType = new AtomicReference<>();
        AtomicReference<byte[]> body = new AtomicReference<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/ai/core/materials", exchange -> {
            contentType.set(exchange.getRequestHeaders().getFirst("Content-Type"));
            body.set(exchange.getRequestBody().readAllBytes());
            byte[] response = "{\"materialId\":\"mat_123\",\"state\":\"ready\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(201, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
        try {
            AgentProperties properties = new AgentProperties();
            properties.setTimeoutMs(5_000);
            String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
            AgentOsGatewayService service = new AgentOsGatewayService(WebClient.builder(), properties, baseUrl);

            Map<String, Object> response = service.postMaterial(
                    "/ai/core/materials",
                    new MockMultipartFile("file", "contract.txt", "text/plain", "probe-contract".getBytes(StandardCharsets.UTF_8))
            );

            assertEquals(201, response.get(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY));
            assertTrue(contentType.get().startsWith("multipart/form-data;boundary="));
            String payload = new String(body.get(), StandardCharsets.UTF_8);
            assertTrue(payload.contains("name=\"file\""));
            assertTrue(payload.contains("filename=\"contract.txt\""));
            assertTrue(payload.contains("probe-contract"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void asyncStartPreservesAcceptedStatusWithoutUsingSynchronousTimeoutSemantics() {
        AgentProperties properties = new AgentProperties();
        properties.setTimeoutMs(240000);
        properties.setAsyncStartTimeoutMs(15000);
        WebClient.Builder builder = WebClient.builder().exchangeFunction(request -> Mono.just(
                jsonResponse(HttpStatus.ACCEPTED,
                        "{\"accepted\":true,\"task\":{\"taskId\":\"task_1\",\"status\":\"pending\"},"
                                + "\"run\":{\"runId\":\"run_1\",\"status\":\"pending\"}}")
        ));
        AgentOsGatewayService service = new AgentOsGatewayService(builder, properties, "http://agentos");

        Map<String, Object> response = service.postAsyncStart(
                "/ai/core/workflows/start-async",
                Map.of("clientRequestId", "request_1")
        );

        assertEquals(202, response.get(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY));
        assertEquals("run_1", ((Map<?, ?>) response.get("run")).get("runId"));
    }

    @Test
    void asyncStartPreservesUpstream503InsteadOfConvertingItTo404() {
        AgentProperties properties = new AgentProperties();
        WebClient.Builder builder = WebClient.builder().exchangeFunction(request -> Mono.just(
                jsonResponse(HttpStatus.SERVICE_UNAVAILABLE,
                        "{\"detail\":\"workflow execution could not be submitted\"}")
        ));
        AgentOsGatewayService service = new AgentOsGatewayService(builder, properties, "http://agentos");

        Map<String, Object> response = service.postAsyncStart(
                "/ai/core/workflows/start-async",
                Map.of("clientRequestId", "request_1")
        );

        assertEquals(503, response.get(AgentOsGatewayService.INTERNAL_HTTP_STATUS_KEY));
        assertEquals("workflow execution could not be submitted", response.get("detail"));
    }

    private ClientResponse jsonResponse(HttpStatus status, String body) {
        return ClientResponse.create(status)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .body(body)
                .build();
    }
}
