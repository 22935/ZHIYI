package com.kinlin.ai.gateway;

import com.kinlin.ai.security.AuthenticatedUserContext;
import com.kinlin.ai.security.SessionActivityProbe;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Non-buffering SSE bridge with separate inactivity and total-duration limits.
 * Setting {@code ai.sse.max-duration-ms} to 0 disables the absolute cap; the
 * inactivity limit still reclaims streams that stop producing events.
 *
 * <p>INT-2F-4B：每条流套 {@link SessionRecheckGate}——建连即校验会话，
 * 周期（默认 3s，含空闲流）按同一 IAM 会话权威复核；撤销/过期/无法确认
 * 时停止受保护事件交付、发出 {@code auth.invalidated} 终止事件并取消上游
 * 订阅。撤销后重连走 filter 真实认证（401），已撤销会话不能恢复流。</p>
 */
@Slf4j
@Service
public class AiSseGatewayService {

    private static final ParameterizedTypeReference<ServerSentEvent<String>> SSE_TYPE =
            new ParameterizedTypeReference<>() { };

    private final WebClient webClient;
    private final Duration idleTimeout;
    private final Duration maximumDuration;
    private final TrustedUserContextForwarder userContextForwarder;
    private final SessionActivityProbe sessionActivityProbe;
    private final Duration sessionRecheckPeriod;
    private final Duration sessionQueryTimeout;
    private final Duration sessionLease;

    // 复核查询专用有界阻塞池：JPA 阻塞调用不占 Reactor 事件线程，
    // 容量上限即并发复核查询上限（超出部分由订阅级 1s 超时 fail-closed 兜住）。
    private final Scheduler sessionRecheckScheduler =
            Schedulers.newBoundedElastic(8, 64, "sse-session-recheck", 60);

    // J1.4C §六：SSE 流生命周期指标，全部无 tag（runId/userId 禁止进入）。
    // idle/max/upstream 三类终止在各自 onErrorResume 转换点计数（事实源头），
    // opened/completed/cancelled/active 在下游订阅生命周期上计数。
    private final AtomicLong activeStreams;
    private final MeterRegistry meterRegistry;

    @Autowired
    public AiSseGatewayService(
            WebClient pythonTransport,
            @Value("${ai.sse.idle-timeout-ms:240000}") long idleTimeoutMs,
            @Value("${ai.sse.max-duration-ms:0}") long maximumDurationMs,
            @Value("${ai.sse.session-recheck-period-ms:3000}") long recheckPeriodMs,
            @Value("${ai.sse.session-query-timeout-ms:1000}") long queryTimeoutMs,
            @Value("${ai.sse.session-lease-ms:5000}") long leaseMs,
            TrustedUserContextForwarder userContextForwarder,
            SessionActivityProbe sessionActivityProbe,
            MeterRegistry meterRegistry
    ) {
        if (idleTimeoutMs <= 0 || maximumDurationMs < 0
                || recheckPeriodMs <= 0 || queryTimeoutMs <= 0 || leaseMs <= 0) {
            throw new IllegalArgumentException("SSE timeouts must be positive, except max-duration-ms where 0 disables the cap");
        }
        this.webClient = pythonTransport;
        this.idleTimeout = Duration.ofMillis(idleTimeoutMs);
        // 0 disables the absolute cap; the idle timeout still terminates dead streams.
        this.maximumDuration = maximumDurationMs > 0 ? Duration.ofMillis(maximumDurationMs) : null;
        this.sessionRecheckPeriod = Duration.ofMillis(recheckPeriodMs);
        this.sessionQueryTimeout = Duration.ofMillis(queryTimeoutMs);
        this.sessionLease = Duration.ofMillis(leaseMs);
        this.userContextForwarder = userContextForwarder;
        this.sessionActivityProbe = sessionActivityProbe;
        this.meterRegistry = meterRegistry;
        this.activeStreams = meterRegistry.gauge("kinlin.sse.streams.active", new AtomicLong());
    }

    /** Test seam: takes a pre-built transport so base-URL wiring stays with {@code PythonClientFactory}. */
    AiSseGatewayService(
            WebClient transport, long idleTimeoutMs, long maximumDurationMs,
            long recheckPeriodMs, long queryTimeoutMs, long leaseMs,
            TrustedUserContextForwarder forwarder, SessionActivityProbe sessionActivityProbe) {
        this(transport, idleTimeoutMs, maximumDurationMs, recheckPeriodMs, queryTimeoutMs, leaseMs,
                forwarder, sessionActivityProbe,
                new io.micrometer.core.instrument.simple.SimpleMeterRegistry());
    }

    public Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> openPost(String path, Object body) {
        var userContext = userContextForwarder.requireCurrent();
        if (userContext.sid() == null || userContext.userId() == null) {
            // 无 sid 的上下文（如兼容 principal 分支）不得建立受保护 SSE 流
            return Mono.just(errorResponse(HttpStatus.UNAUTHORIZED, "AI_STREAM_SESSION_REQUIRED"));
        }
        return webClient.post()
                .uri(path)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .headers(headers -> userContextForwarder.apply(headers, userContext))
                .bodyValue(body == null ? Map.of() : body)
                .retrieve()
                .onStatus(HttpStatusCode::isError, upstream -> upstreamError(upstream.statusCode()))
                .toEntityFlux(SSE_TYPE)
                .transform(response -> toDownstreamResponse(response, userContext))
                .onErrorResume(this::mapConnectionError);
    }

    /** Open the RuntimeEvent stream without introducing a second event source or buffering layer. */
    public Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> openGet(String path) {
        var userContext = userContextForwarder.requireCurrent();
        if (userContext.sid() == null || userContext.userId() == null) {
            return Mono.just(errorResponse(HttpStatus.UNAUTHORIZED, "AI_STREAM_SESSION_REQUIRED"));
        }
        return webClient.get()
                .uri(path)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .headers(headers -> userContextForwarder.apply(headers, userContext))
                .retrieve()
                .onStatus(HttpStatusCode::isError, upstream -> upstreamError(upstream.statusCode()))
                .toEntityFlux(SSE_TYPE)
                .transform(response -> toDownstreamResponse(response, userContext))
                .onErrorResume(this::mapConnectionError);
    }

    private Mono<? extends Throwable> upstreamError(HttpStatusCode statusCode) {
        return Mono.error(new SseUpstreamStatusException(statusCode.value()));
    }

    private Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> toDownstreamResponse(
            Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> upstreamResponse,
            AuthenticatedUserContext userContext
    ) {
        return upstreamResponse.map(upstream -> {
            Flux<ServerSentEvent<String>> body = upstream.getBody() == null
                    ? Flux.empty()
                    : upstream.getBody();
            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_EVENT_STREAM)
                    .header("Cache-Control", "no-cache, no-transform")
                    .header("X-Accel-Buffering", "no")
                    .body(instrument(withSessionGate(
                            withTimeouts(body, Schedulers.parallel()), userContext, Schedulers.parallel())));
        });
    }

    // Both clocks share an explicit scheduler. Production retains Reactor's
    // parallel clock; tests can advance time without loopback/CPU jitter.
    Flux<ServerSentEvent<String>> withTimeouts(Flux<ServerSentEvent<String>> body, Scheduler clock) {
        Flux<ServerSentEvent<String>> bounded = body
                    .timeout(idleTimeout, Flux.error(new SseIdleTimeoutException()), clock);
        if (maximumDuration != null) {
            bounded = bounded.takeUntilOther(Mono.delay(maximumDuration, clock)
                            .flatMap(ignored -> Mono.<Void>error(new SseMaximumDurationException())));
        }
        return bounded
                    .onErrorResume(SseIdleTimeoutException.class,
                            ignored -> Flux.just(terminalErrorEvent("SSE_IDLE_TIMEOUT",
                                    "kinlin.sse.streams.idle_timeout")))
                    .onErrorResume(SseMaximumDurationException.class,
                            ignored -> Flux.just(terminalErrorEvent("SSE_MAX_DURATION",
                                    "kinlin.sse.streams.max_duration")))
                    .onErrorResume(error -> {
                        log.warn("SSE upstream stream terminated. type={}", error.getClass().getSimpleName());
                        meterRegistry.counter("kinlin.sse.streams.upstream_error").increment();
                        return Flux.just(errorEvent("AI_STREAM_INTERRUPTED"));
                    })
                    .doOnCancel(() -> log.info("SSE downstream cancelled; upstream subscription cancelled"));

    }

    /**
     * 会话交付门（INT-2F-4B）：建连捕获的 sid/userId 周期复核；
     * 终止时尽力发送不含业务数据的 {@code auth.invalidated} 事件后完成流。
     */
    Flux<ServerSentEvent<String>> withSessionGate(
            Flux<ServerSentEvent<String>> body, AuthenticatedUserContext userContext, Scheduler clock) {
        SessionRecheckGate gate = new SessionRecheckGate(
                sessionActivityProbe, userContext.sid(), userContext.userId(),
                sessionRecheckPeriod, sessionQueryTimeout, sessionLease,
                sessionRecheckScheduler,
                () -> meterRegistry.counter("kinlin.sse.streams.session_revoked").increment());
        return Flux.defer(() -> {
            gate.start(clock);
            return body
                    .concatMap(gate::admit)
                    .takeUntilOther(gate.revocationSignal())
                    .onErrorResume(SessionRecheckGate.SessionRevokedException.class,
                            ignored -> Flux.empty())
                    .concatWith(Flux.defer(() -> gate.isRevoked()
                            ? Flux.just(sessionInvalidatedEvent())
                            : Flux.empty()))
                    .doFinally(signal -> gate.close());
        });
    }

    private ServerSentEvent<String> sessionInvalidatedEvent() {
        return ServerSentEvent.<String>builder("{\"code\":\"AUTH_SESSION_INVALIDATED\"}")
                .event("auth.invalidated")
                .build();
    }

    private Flux<ServerSentEvent<String>> instrument(Flux<ServerSentEvent<String>> stream) {
        return stream
                .doOnSubscribe(ignored -> {
                    meterRegistry.counter("kinlin.sse.streams.opened").increment();
                    activeStreams.incrementAndGet();
                })
                .doOnCancel(() -> {
                    meterRegistry.counter("kinlin.sse.streams.cancelled").increment();
                    activeStreams.decrementAndGet();
                })
                .doFinally(signal -> {
                    if (signal == SignalType.ON_COMPLETE) {
                        meterRegistry.counter("kinlin.sse.streams.completed").increment();
                        activeStreams.decrementAndGet();
                    } else if (signal == SignalType.ON_ERROR) {
                        activeStreams.decrementAndGet();
                    }
                });
    }

    /** 终止类错误事件：计数 + 错误事件一次完成（idle/max 专用）。 */
    private ServerSentEvent<String> terminalErrorEvent(String code, String counterName) {
        meterRegistry.counter(counterName).increment();
        return errorEvent(code);
    }

    private Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> mapConnectionError(Throwable error) {
        if (error instanceof SseUpstreamStatusException statusError) {
            return Mono.just(errorResponse(
                    statusError.status < 500 ? HttpStatus.valueOf(statusError.status) : HttpStatus.BAD_GATEWAY,
                    statusError.status < 500 ? "AI_STREAM_REJECTED" : "AI_STREAM_UPSTREAM_ERROR"
            ));
        }
        log.warn("SSE upstream connection failed. type={}", error.getClass().getSimpleName());
        return Mono.just(errorResponse(HttpStatus.SERVICE_UNAVAILABLE, "AI_STREAM_UNAVAILABLE"));
    }

    private ResponseEntity<Flux<ServerSentEvent<String>>> errorResponse(HttpStatus status, String code) {
        return ResponseEntity.status(status)
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header("Cache-Control", "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(Flux.just(errorEvent(code)));
    }

    private ServerSentEvent<String> errorEvent(String code) {
        return ServerSentEvent.builder("{\"error\":\"" + code + "\"}").event("error").build();
    }

    private static final class SseIdleTimeoutException extends RuntimeException { }

    private static final class SseMaximumDurationException extends RuntimeException { }

    private static final class SseUpstreamStatusException extends RuntimeException {
        private final int status;

        private SseUpstreamStatusException(int status) {
            this.status = status;
        }
    }
}
