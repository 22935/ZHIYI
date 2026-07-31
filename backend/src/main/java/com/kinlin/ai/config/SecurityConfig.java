package com.kinlin.ai.config;

import com.kinlin.ai.filter.JwtAuthenticationFilter;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import com.kinlin.ai.observability.TraceContext;

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
                // Only the container's continuation of an already-authorized reactive response.
                .dispatcherTypeMatchers(DispatcherType.ASYNC).permitAll()
                // 允许OPTIONS预检请求（CORS预检）
                .requestMatchers(org.springframework.http.HttpMethod.OPTIONS, "/**").permitAll()
                // 公开接口
                .requestMatchers(
                    "/health",
                    "/health/**",
                    "/actuator/health/**",
                    "/swagger-ui/**",
                    "/v3/api-docs/**",
                    "/ws/**",
                    "/auth/**"
                ).permitAll()
                // 其他接口需要认证
                .anyRequest().authenticated()
            )
            .exceptionHandling(exceptions -> exceptions.authenticationEntryPoint((request, response, error) -> {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                String traceId = TraceContext.acceptedOrNew(response.getHeader(TraceContext.HEADER));
                response.setHeader(TraceContext.HEADER, traceId);
                response.getWriter().write("{\"error\":\"unauthorized\",\"traceId\":\"" + traceId + "\"}");
            }))
            // 添加JWT过滤器（在UsernamePasswordAuthenticationFilter之前）
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);
        
        return http.build();
    }
}

