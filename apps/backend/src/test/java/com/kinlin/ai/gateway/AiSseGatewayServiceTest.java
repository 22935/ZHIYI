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
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AiSseGatewayServiceTest {

    private HttpServer server;
    private String baseUrl;
    private ExecutorService serverExecutor;

    private final com.kinlin.ai.service.LoginSessionService loginSessionService =
            org.mockito.Mockito.mock(com.kinlin.ai.service.LoginSessionService.class);

    @BeforeEach
    void startServer() throws IOException {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        new AuthenticatedUserContext(UUID.randomUUID(), "sse-test", "USER",
                                UUID.randomUUID(), null, null),
                        null,
                        java.util.List.of()
                )
        );
        org.mockito.Mockito.when(loginSessionService.isSessionActive(
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any()))
                .thenReturn(true);
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        serverExecutor = Executors.newCachedThreadPool();
        server.setExecutor(serverExecutor);
        server.createContext("/ai/events", exchange -> stream(exchange, List.of(
                ": heartbeat\n\n",
                "data: {\"delta\":\"hello\"}\n\n",
                "data: [DONE]\n\n"
        ), 5));
        server.createContext("/ai/runtime-events", exchange -> stream(exchange, List.of(
                "event: model.output.delta\ndata: {\"delta\":\"A\"}\n\n",
                "event: model.output.delta\ndata: {\"delta\":\"B\"}\n\n",
                "event: node.completed\ndata: {\"runId\":\"run-1\"}\n\n"
        ), 300));
        server.createContext("/ai/runtime-events-timeline", exchange -> streamWithDelays(exchange, List.of(
                "event: model.output.delta\ndata: {\"delta\":\"A\"}\n\n",
                "event: model.output.delta\ndata: {\"delta\":\"B\"}\n\n",
                "event: node.completed\ndata: {\"runId\":\"run-1\"}\n\n"
        ), List.of(0L, 300L, 800L)));
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
        serverExecutor.shutdownNow();
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
        VirtualTimeScheduler idleClock = VirtualTimeScheduler.create();
        try {
            VirtualTimeScheduler clock = idleClock;
            StepVerifier.withVirtualTime(() -> service(40, 1_000).withTimeouts(Flux.never(), clock),
                            () -> clock, Long.MAX_VALUE)
                    .expectSubscription().expectNoEvent(Duration.ofMillis(39))
                    .thenAwait(Duration.ofMillis(1))
                    .expectNextMatches(e -> e.data().contains("SSE_IDLE_TIMEOUT"))
                    .verifyComplete();
        } finally {
            idleClock.dispose();
        }
        // Keep the original 25ms heartbeat / 80ms idle / 70ms maximum case,
        // then strengthen it: 40ms idle must refresh at 25 and 50ms, while
        // absolute maximum still terminates at 70ms, not 120ms.
        for (long idleMs : new long[]{80, 40}) {
            VirtualTimeScheduler clock = VirtualTimeScheduler.create();
            try {
                StepVerifier.withVirtualTime(() -> service(idleMs, 70).withTimeouts(
                                Flux.interval(Duration.ofMillis(25), clock)
                                        .map(i -> ServerSentEvent.<String>builder().comment("heartbeat").build()), clock),
                                () -> clock, Long.MAX_VALUE)
                        .expectSubscription().expectNoEvent(Duration.ofMillis(24))
                        .thenAwait(Duration.ofMillis(1))
                        .expectNextMatches(e -> "heartbeat".equals(e.comment()))
                        .expectNoEvent(Duration.ofMillis(24)).thenAwait(Duration.ofMillis(1))
                        .expectNextMatches(e -> "heartbeat".equals(e.comment()))
                        .expectNoEvent(Duration.ofMillis(19)).thenAwait(Duration.ofMillis(1))
                        .expectNextMatches(e -> e.data().contains("SSE_MAX_DURATION"))
                        .verifyComplete();
            } finally {
                clock.dispose();
            }
        }
    }

    @Test
    void zeroMaximumDurationDisablesTheAbsoluteCap() {
        VirtualTimeScheduler clock = VirtualTimeScheduler.create();
        try {
            StepVerifier.withVirtualTime(() -> service(80, 0).withTimeouts(
                            Flux.interval(Duration.ofMillis(25), clock)
                                    .map(i -> ServerSentEvent.<String>builder().comment("heartbeat").build()), clock),
                            () -> clock, Long.MAX_VALUE)
                    .expectSubscription().expectNoEvent(Duration.ofMillis(24))
                    .thenAwait(Duration.ofMillis(1))
                    .expectNextMatches(e -> "heartbeat".equals(e.comment()))
                    .expectNoEvent(Duration.ofMillis(24)).thenAwait(Duration.ofMillis(1))
                    .expectNextMatches(e -> "heartbeat".equals(e.comment()))
                    // 70ms was the old absolute cap; with 0 the stream keeps producing.
                    .expectNoEvent(Duration.ofMillis(24)).thenAwait(Duration.ofMillis(1))
                    .expectNextMatches(e -> "heartbeat".equals(e.comment()))
                    .thenCancel()
                    .verify();
        } finally {
            clock.dispose();
        }
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

    @Test
    void runtimeEventGetStreamsBeforeUpstreamCompletes() {
        ResponseEntity<Flux<ServerSentEvent<String>>> response = service(1_000, 5_000)
                .openGet("/ai/runtime-events-timeline").block(Duration.ofSeconds(1));

        long started = System.nanoTime();
        List<ServerSentEvent<String>> firstTwo = response.getBody()
                .take(2)
                .collectList()
                .block(Duration.ofSeconds(2));
        long elapsedMs = (System.nanoTime() - started) / 1_000_000;

        assertEquals(200, response.getStatusCode().value());
        assertEquals(2, firstTwo.size());
        assertEquals("model.output.delta", firstTwo.get(0).event());
        assertEquals("{\"delta\":\"A\"}", firstTwo.get(0).data());
        assertEquals("{\"delta\":\"B\"}", firstTwo.get(1).data());
        assertTrue(elapsedMs < 700, "gateway buffered A/B until upstream completion: " + elapsedMs + "ms");
    }

    private AiSseGatewayService service(long idleMs, long maximumMs) {
        return service(idleMs, maximumMs, new io.micrometer.core.instrument.simple.SimpleMeterRegistry());
    }

    private AiSseGatewayService service(long idleMs, long maximumMs,
                                        io.micrometer.core.instrument.MeterRegistry registry) {
        // 会话复核参数取合同默认值：周期远长于本类各用例时长，不干扰既有超时断言
        return new AiSseGatewayService(WebClient.builder().baseUrl(baseUrl).build(), idleMs, maximumMs,
                3000, 1000, 5000, new TrustedUserContextForwarder(), loginSessionService, registry);
    }

    private static double counter(io.micrometer.core.instrument.MeterRegistry registry, String name) {
        return registry.find(name).counters().stream().mapToDouble(c -> c.count()).sum();
    }

    private static double gauge(io.micrometer.core.instrument.MeterRegistry registry, String name) {
        return registry.find(name).gauge() == null ? 0.0 : registry.find(name).gauge().value();
    }

    @Test
    void streamLifecycleCountersTrackOpenCompleteIdleMaxAndActiveGauge() {
        io.micrometer.core.instrument.simple.SimpleMeterRegistry registry =
                new io.micrometer.core.instrument.simple.SimpleMeterRegistry();

        // 正常完成：opened=1、completed=1、active 回 0
        ResponseEntity<Flux<ServerSentEvent<String>>> ok = service(200, 1_000, registry)
                .openPost("/ai/events", java.util.Map.of()).block(Duration.ofSeconds(1));
        ok.getBody().collectList().block(Duration.ofSeconds(1));
        assertEquals(1.0, counter(registry, "kinlin.sse.streams.opened"));
        assertEquals(1.0, counter(registry, "kinlin.sse.streams.completed"));
        assertEquals(0.0, gauge(registry, "kinlin.sse.streams.active"));

        // idle timeout：专用计数器 + active 回 0
        ResponseEntity<Flux<ServerSentEvent<String>>> idle = service(40, 1_000, registry)
                .openPost("/ai/idle", java.util.Map.of()).block(Duration.ofSeconds(1));
        idle.getBody().collectList().block(Duration.ofSeconds(1));
        assertEquals(1.0, counter(registry, "kinlin.sse.streams.idle_timeout"));

        // max duration：专用计数器
        ResponseEntity<Flux<ServerSentEvent<String>>> maximum = service(80, 70, registry)
                .openPost("/ai/long", java.util.Map.of()).block(Duration.ofSeconds(1));
        maximum.getBody().collectList().block(Duration.ofSeconds(1));
        assertEquals(1.0, counter(registry, "kinlin.sse.streams.max_duration"));

        // 三条流全部终结后，active gauge 必须归零（泄漏防线）
        assertEquals(0.0, gauge(registry, "kinlin.sse.streams.active"));
    }

    @Test
    void downstreamCancelIsCountedAndReleasesActiveStream() throws Exception {
        io.micrometer.core.instrument.simple.SimpleMeterRegistry registry =
                new io.micrometer.core.instrument.simple.SimpleMeterRegistry();
        reactor.core.Disposable subscription = service(1_000, 5_000, registry)
                .openGet("/ai/runtime-events-timeline").block(Duration.ofSeconds(1))
                .getBody()
                .subscribe();

        // 订阅/取消是异步传播，轮询等待计数落地（有界，不无限等）
        awaitValue(registry, "kinlin.sse.streams.active", 1.0);
        subscription.dispose();
        awaitValue(registry, "kinlin.sse.streams.cancelled", 1.0);
        awaitValue(registry, "kinlin.sse.streams.active", 0.0);
    }

    private static void awaitValue(io.micrometer.core.instrument.MeterRegistry registry,
                                   String name, double expected) throws InterruptedException {
        long deadline = System.currentTimeMillis() + 2_000;
        double current;
        do {
            current = "kinlin.sse.streams.active".equals(name)
                    ? gauge(registry, name)
                    : counter(registry, name);
            if (Double.compare(current, expected) == 0) {
                return;
            }
            Thread.sleep(20);
        } while (System.currentTimeMillis() < deadline);
        org.junit.jupiter.api.Assertions.assertEquals(expected, current, name + " 未在时限内到达");
    }

    @Test
    void preStreamUpstreamErrorsDoNotTouchStreamCounters() {
        io.micrometer.core.instrument.simple.SimpleMeterRegistry registry =
                new io.micrometer.core.instrument.simple.SimpleMeterRegistry();
        // 422 在流建立前被拒绝（errorResponse 路径）：不算 opened，也不产生 active
        ResponseEntity<Flux<ServerSentEvent<String>>> rejected = service(100, 1_000, registry)
                .openPost("/ai/rejected", java.util.Map.of()).block(Duration.ofSeconds(1));
        rejected.getBody().collectList().block(Duration.ofSeconds(1));

        assertEquals(0.0, counter(registry, "kinlin.sse.streams.opened"));
        assertEquals(0.0, gauge(registry, "kinlin.sse.streams.active"));
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

    private void streamWithDelays(HttpExchange exchange, List<String> events, List<Long> delaysMs) throws IOException {
        exchange.getRequestBody().readAllBytes();
        exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
        exchange.sendResponseHeaders(200, 0);
        try {
            for (int index = 0; index < events.size(); index++) {
                try {
                    Thread.sleep(delaysMs.get(index));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    break;
                }
                exchange.getResponseBody().write(events.get(index).getBytes(StandardCharsets.UTF_8));
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
