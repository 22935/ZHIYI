package com.kinlin.ai.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import org.slf4j.MDC;

/**
 * 请求日志过滤器
 * 记录所有HTTP请求
 */
@Slf4j
@Component
public class RequestLoggingFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        long startTime = System.currentTimeMillis();
        
        try {
            filterChain.doFilter(request, response);
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            MDC.put("http_method", request.getMethod());
            MDC.put("path", request.getRequestURI());
            MDC.put("status", Integer.toString(response.getStatus()));
            MDC.put("duration_ms", Long.toString(duration));
            try {
                log.info("HTTP request completed");
            } finally {
                MDC.remove("http_method");
                MDC.remove("path");
                MDC.remove("status");
                MDC.remove("duration_ms");
            }
        }
    }
}

