package com.kinlin.ai.filter;

import com.kinlin.ai.util.JwtUtil;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.UUID;

/**
 * JWT认证过滤器
 * 从请求头中提取Token并验证
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtUtil jwtUtil;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        
        // Skip public auth paths and local/demo AgentOS proxy paths.
        // Production deployments must tighten this before deployment.
        String path = request.getRequestURI();
        if (path != null && (
            path.startsWith("/auth/") || path.equals("/auth") ||
            path.startsWith("/ai/core/") || path.equals("/ai/core") ||
            path.equals("/ai/chat/workflows/upgrade") ||
            path.startsWith("/health") ||
            path.startsWith("/swagger-ui/") ||
            path.startsWith("/v3/api-docs/") ||
            path.startsWith("/ws/")
        )) {
            filterChain.doFilter(request, response);
            return;
        }
        
        String authHeader = request.getHeader("Authorization");
        
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring(7);
            
            try {
                String username = jwtUtil.getUsernameFromToken(token);
                UUID userId = jwtUtil.getUserIdFromToken(token);
                
                if (username != null && SecurityContextHolder.getContext().getAuthentication() == null) {
                    if (jwtUtil.validateToken(token, username)) {
                        // 设置用户上下文
                        UsernamePasswordAuthenticationToken authentication =
                                new UsernamePasswordAuthenticationToken(
                                        userId,
                                        null,
                                        new ArrayList<>()
                                );
                        authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
                        SecurityContextHolder.getContext().setAuthentication(authentication);
                        
                        // 设置用户ID到请求头（用于后续处理）
                        request.setAttribute("userId", userId);
                    }
                }
            } catch (Exception e) {
                log.error("JWT验证失败", e);
                // 对于认证路径，即使Token验证失败也继续执行
                // 对于其他路径，Security会处理未认证的请求
            }
        }
        
        filterChain.doFilter(request, response);
    }
}

