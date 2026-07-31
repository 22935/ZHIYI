package com.kinlin.ai.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;
import java.util.UUID;

/** 认证用户工具类 — 从 Spring Security SecurityContextHolder 中提取当前已认证用户 ID */
public final class AuthenticatedUser {

    private AuthenticatedUser() {
    }

    public static Optional<UUID> currentUserId() {
        return currentContext().map(AuthenticatedUserContext::userId);
    }

    public static Optional<AuthenticatedUserContext> currentContext() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || authentication.getPrincipal() == null) {
            return Optional.empty();
        }

        Object principal = authentication.getPrincipal();
        if (principal instanceof AuthenticatedUserContext context) {
            return Optional.of(context);
        }
        if (principal instanceof UUID uuid) {
            return Optional.of(new AuthenticatedUserContext(uuid, uuid.toString(), "USER", null, null));
        }

        if (principal instanceof String text && !"anonymousUser".equals(text)) {
            try {
                UUID userId = UUID.fromString(text);
                return Optional.of(new AuthenticatedUserContext(userId, text, "USER", null, null));
            } catch (IllegalArgumentException ignored) {
                return Optional.empty();
            }
        }

        return Optional.empty();
    }
}
