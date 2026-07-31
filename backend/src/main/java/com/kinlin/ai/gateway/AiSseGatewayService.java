package com.kinlin.ai.gateway;

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

import java.time.Duration;
import java.util.Map;

/** Non-buffering SSE bridge with separate inactivity and total-duration limits. */
@Slf4j
@Service
public class AiSseGatewayService {

    private static final ParameterizedTypeReference<ServerSentEvent<String>> SSE_TYPE =
            new ParameterizedTypeReference<>() { };

    private final WebClient webClient;
    private final Duration idleTimeout;
    private final Duration maximumDuration;
    private final TrustedUserContextForwarder userContextForwarder;

    @Autowired
    public AiSseGatewayService(
            WebClient.Builder webClientBuilder,
            @Value("${ai.service.url:http://localhost:8000}") String aiServiceUrl,
            @Value("${ai.sse.idle-timeout-ms:240000}") long idleTimeoutMs,
            @Value("${ai.sse.max-duration-ms:1800000}") long maximumDurationMs,
            TrustedUserContextForwarder userContextForwarder
    ) {
        if (idleTimeoutMs <= 0 || maximumDurationMs <= 0) {
            throw new IllegalArgumentException("SSE timeouts must be positive");
        }
        this.webClient = webClientBuilder.baseUrl(aiServiceUrl).build();
        this.idleTimeout = Duration.ofMillis(idleTimeoutMs);
        this.maximumDuration = Duration.ofMillis(maximumDurationMs);
        this.userContextForwarder = userContextForwarder;
    }

    AiSseGatewayService(WebClient.Builder builder, String url, long idleTimeoutMs, long maximumDurationMs) {
        this(builder, url, idleTimeoutMs, maximumDurationMs, new TrustedUserContextForwarder());
    }

    public Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> openPost(String path, Object body) {
        var userContext = userContextForwarder.requireCurrent();
        return webClient.post()
                .uri(path)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .headers(headers -> userContextForwarder.apply(headers, userContext))
                .bodyValue(body == null ? Map.of() : body)
                .retrieve()
                .onStatus(HttpStatusCode::isError, upstream -> {
                    int status = upstream.statusCode().value();
                    return upstream.releaseBody().then(Mono.error(new SseUpstreamStatusException(status)));
                })
                .toEntityFlux(SSE_TYPE)
                .map(upstream -> {
                    Flux<ServerSentEvent<String>> stream = upstream.getBody()
                            .timeout(idleTimeout, Flux.error(new SseIdleTimeoutException()))
                            .takeUntilOther(Mono.delay(maximumDuration)
                                    .flatMap(ignored -> Mono.<Void>error(new SseMaximumDurationException())))
                            .onErrorResume(SseIdleTimeoutException.class,
                                    ignored -> Flux.just(errorEvent("SSE_IDLE_TIMEOUT")))
                            .onErrorResume(SseMaximumDurationException.class,
                                    ignored -> Flux.just(errorEvent("SSE_MAX_DURATION")))
                            .onErrorResume(error -> {
                                log.warn("SSE upstream stream terminated. type={}", error.getClass().getSimpleName());
                                return Flux.just(errorEvent("AI_STREAM_INTERRUPTED"));
                            })
                            .doOnCancel(() -> log.info("SSE downstream cancelled; upstream subscription cancelled"));

                    return ResponseEntity.ok()
                            .contentType(MediaType.TEXT_EVENT_STREAM)
                            .header("Cache-Control", "no-cache, no-transform")
                            .header("X-Accel-Buffering", "no")
                            .body(stream);
                })
                .onErrorResume(SseUpstreamStatusException.class, error -> Mono.just(errorResponse(
                        error.status < 500 ? HttpStatus.valueOf(error.status) : HttpStatus.BAD_GATEWAY,
                        error.status < 500 ? "AI_STREAM_REJECTED" : "AI_STREAM_UPSTREAM_ERROR"
                )))
                .onErrorResume(error -> {
                    log.warn("SSE upstream connection failed. type={}", error.getClass().getSimpleName());
                    return Mono.just(errorResponse(HttpStatus.SERVICE_UNAVAILABLE, "AI_STREAM_UNAVAILABLE"));
                });
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
