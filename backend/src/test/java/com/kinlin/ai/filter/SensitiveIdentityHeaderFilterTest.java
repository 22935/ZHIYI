package com.kinlin.ai.filter;

import jakarta.servlet.ServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.util.Collections;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

class SensitiveIdentityHeaderFilterTest {

    @Test
    void removesClientIdentityAndInternalHeadersBeforeControllers() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/ai/chat/text");
        request.addHeader("Authorization", "Bearer safe-to-keep");
        request.addHeader("X-User-Id", "forged-user");
        request.addHeader("X-User-Role", "ADMIN");
        request.addHeader("X-Internal-Service-Token", "forged-token");
        AtomicReference<ServletRequest> downstream = new AtomicReference<>();

        new SensitiveIdentityHeaderFilter().doFilter(
                request,
                new MockHttpServletResponse(),
                (wrapped, response) -> downstream.set(wrapped)
        );

        jakarta.servlet.http.HttpServletRequest wrapped =
                (jakarta.servlet.http.HttpServletRequest) downstream.get();
        assertEquals("Bearer safe-to-keep", wrapped.getHeader("Authorization"));
        assertNull(wrapped.getHeader("X-User-Id"));
        assertNull(wrapped.getHeader("X-User-Role"));
        assertNull(wrapped.getHeader("X-Internal-Service-Token"));
        assertFalse(Collections.list(wrapped.getHeaderNames()).contains("X-User-Id"));
    }
}
