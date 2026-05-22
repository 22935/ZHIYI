package com.kinlin.ai.config;

import com.kinlin.ai.filter.JwtAuthenticationFilter;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * 安全配置类
 * 配置JWT认证和授权
 */
@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .cors(cors -> {}) // 启用CORS支持（使用WebConfig中的CORS配置）
            .sessionManagement(session -> 
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // 允许OPTIONS预检请求（CORS预检）
                .requestMatchers(org.springframework.http.HttpMethod.OPTIONS, "/**").permitAll()
                // 公开接口
                .requestMatchers(
                    "/health",
                    "/swagger-ui/**",
                    "/v3/api-docs/**",
                    "/ws/**",
                    "/auth/**",  // 允许所有 /auth 路径（登录、注册、验证Token）
                    // Local/demo AgentOS and Python AI proxy allowance.
                    // Production deployments must require auth for these workflow routes.
                    "/ai/core/**",
                    "/ai/chat/workflows/upgrade"
                ).permitAll()
                // 其他接口需要认证
                .anyRequest().authenticated()
            )
            // 添加JWT过滤器（在UsernamePasswordAuthenticationFilter之前）
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);
        
        return http.build();
    }
}

