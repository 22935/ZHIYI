package com.kinlin.ai.interceptor;

import com.kinlin.ai.security.AuthenticatedUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.util.UUID;

/**
 * 用户上下文拦截器
 * 从请求头中提取用户ID并设置到上下文
 */
@Slf4j
@Component
public class UserContextInterceptor implements HandlerInterceptor {

    private static final ThreadLocal<UUID> USER_ID_CONTEXT = new ThreadLocal<>();

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler
    ) {
        UUID authenticatedUserId = AuthenticatedUser.currentUserId()
                .orElseGet(() -> (UUID) request.getAttribute("userId"));
        if (authenticatedUserId != null) {
            USER_ID_CONTEXT.set(authenticatedUserId);
            return true;
        }

        String userIdHeader = request.getHeader("X-User-Id");
        if (userIdHeader != null && !userIdHeader.isEmpty()) {
            try {
                UUID userId = UUID.fromString(userIdHeader);
                USER_ID_CONTEXT.set(userId);
            } catch (IllegalArgumentException e) {
                log.warn("Invalid user ID in header: {}", userIdHeader);
            }
        }
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex
    ) {
        USER_ID_CONTEXT.remove();
    }

    /**
     * 获取当前用户ID
     */
    public static UUID getCurrentUserId() {
        return USER_ID_CONTEXT.get();
    }
}

