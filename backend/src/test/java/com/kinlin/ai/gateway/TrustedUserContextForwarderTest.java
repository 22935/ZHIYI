package com.kinlin.ai.gateway;

import com.kinlin.ai.security.AuthenticatedUserContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TrustedUserContextForwarderTest {

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void rebuildsIdentityFromAuthenticatedPrincipal() {
        UUID userId = UUID.randomUUID();
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        new AuthenticatedUserContext(userId, "alice", "USER", null, null),
                        null,
                        List.of()
                )
        );
        HttpHeaders headers = new HttpHeaders();
        headers.set(AiGatewayHeaders.AUTHENTICATED_USER_ID, UUID.randomUUID().toString());

        new TrustedUserContextForwarder().apply(headers);

        assertEquals(userId.toString(), headers.getFirst(AiGatewayHeaders.AUTHENTICATED_USER_ID));
        assertEquals("alice", headers.getFirst(AiGatewayHeaders.AUTHENTICATED_USER_SUBJECT));
        assertEquals("USER", headers.getFirst(AiGatewayHeaders.AUTHENTICATED_USER_ROLE));
    }

    @Test
    void failsWhenAuthenticationContextIsMissing() {
        assertThrows(IllegalStateException.class,
                () -> new TrustedUserContextForwarder().apply(new HttpHeaders()));
    }
}
