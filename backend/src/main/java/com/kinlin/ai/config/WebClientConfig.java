package com.kinlin.ai.config;

import com.kinlin.ai.gateway.PythonServiceAuthentication;
import com.kinlin.ai.gateway.TrustedUserContextForwarder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import com.kinlin.ai.observability.TraceContext;

import java.time.Duration;

/**
 * WebClient配置类
 * 用于调用Python AI服务
 */
@Configuration
public class WebClientConfig {

    @Value("${ai.service.url:http://localhost:8000}")
    private String aiServiceUrl;

    @Value("${ai.service.connect-timeout:15000}")
    private int connectTimeoutMs;

    @Bean
    public WebClient.Builder webClientBuilder(
            PythonServiceAuthentication authentication,
            TrustedUserContextForwarder userContextForwarder
    ) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, connectTimeoutMs);
        return WebClient.builder()
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .baseUrl(aiServiceUrl)
                .codecs(configurer -> configurer
                        .defaultCodecs()
                        .maxInMemorySize(10 * 1024 * 1024)) // 10MB
                .defaultHeader("Content-Type", "application/json")
                .filter((request, next) -> {
                    ClientRequest authenticated = ClientRequest.from(request)
                            .headers(headers -> {
                                authentication.apply(headers);
                                if (!headers.containsKey(TraceContext.HEADER)) {
                                    headers.set(TraceContext.HEADER, TraceContext.currentTraceId());
                                }
                                if (!request.url().getPath().startsWith("/health")
                                        && !headers.containsKey(com.kinlin.ai.gateway.AiGatewayHeaders.AUTHENTICATED_USER_ID)) {
                                    userContextForwarder.apply(headers);
                                }
                            })
                            .build();
                    return next.exchange(authenticated);
                });
    }

    @Bean
    public WebClient webClient(WebClient.Builder builder) {
        return builder.build();
    }
}
