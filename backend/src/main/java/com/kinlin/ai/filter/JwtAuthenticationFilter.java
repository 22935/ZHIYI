package com.kinlin.ai.filter;

import com.kinlin.ai.util.JwtUtil;
import com.kinlin.ai.security.AuthenticatedUserContext;
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
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.slf4j.MDC;

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
        
        // Only authentication and health/documentation endpoints are public.
        String path = request.getRequestURI();
        if (path != null && (
            path.startsWith("/auth/") || path.equals("/auth") ||
            path.startsWith("/health") ||
            path.startsWith("/actuator/health") ||
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
                String role = jwtUtil.getRoleFromToken(token);
                
                if (username != null && SecurityContextHolder.getContext().getAuthentication() == null) {
                    if (jwtUtil.validateToken(token, username)) {
                        // 设置用户上下文
                        UsernamePasswordAuthenticationToken authentication =
                                new UsernamePasswordAuthenticationToken(
                                        new AuthenticatedUserContext(userId, username, role, null, MDC.get("trace_id")),
                                        null,
                                        java.util.List.of(new SimpleGrantedAuthority("ROLE_" + role))
                                );
                        authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
                        SecurityContextHolder.getContext().setAuthentication(authentication);
                        
                        // 设置用户ID到请求头（用于后续处理）
                        request.setAttribute("userId", userId);
                    }
                }
            } catch (Exception e) {
                log.debug("JWT validation rejected: {}", e.getClass().getSimpleName());
            }
        }
        
        filterChain.doFilter(request, response);
    }
}

