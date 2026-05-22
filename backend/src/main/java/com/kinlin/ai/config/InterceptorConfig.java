package com.kinlin.ai.config;

import com.kinlin.ai.interceptor.RateLimitInterceptor;
import com.kinlin.ai.interceptor.UserContextInterceptor;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * 拦截器配置类
 */
@Configuration
@RequiredArgsConstructor
public class InterceptorConfig implements WebMvcConfigurer {

    private final UserContextInterceptor userContextInterceptor;
    private final RateLimitInterceptor rateLimitInterceptor;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Local/demo AgentOS proxy paths are excluded. Production should require auth here.
        // 限流拦截器（最先执行）
        registry.addInterceptor(rateLimitInterceptor)
                .addPathPatterns("/**")
                .excludePathPatterns("/health", "/swagger-ui/**", "/v3/api-docs/**", "/ws/**", "/auth/**", "/ai/core/**", "/ai/chat/workflows/upgrade");
        
        // 用户上下文拦截器
        registry.addInterceptor(userContextInterceptor)
                .addPathPatterns("/**")
                .excludePathPatterns("/health", "/swagger-ui/**", "/v3/api-docs/**", "/auth/**", "/ai/core/**", "/ai/chat/workflows/upgrade");
    }
}

