package com.kinlin.ai.security;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuthenticatedUserTest {

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void currentUserIdReadsUuidPrincipal() {
        UUID userId = UUID.randomUUID();
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(userId, null, List.of())
        );

        assertEquals(userId, AuthenticatedUser.currentUserId().orElseThrow());
    }

    @Test
    void currentUserIdIgnoresAnonymousPrincipal() {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken("anonymousUser", null, List.of())
        );

        assertTrue(AuthenticatedUser.currentUserId().isEmpty());
    }

    @Test
    void currentContextReadsTrustedPrincipal() {
        UUID userId = UUID.randomUUID();
        AuthenticatedUserContext principal = new AuthenticatedUserContext(
                userId, "alice", "USER", null, null
        );
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(principal, null, List.of())
        );

        assertEquals(principal, AuthenticatedUser.currentContext().orElseThrow());
    }
}
