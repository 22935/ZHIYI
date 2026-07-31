package com.kinlin.ai.util;

import io.jsonwebtoken.JwtException;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JwtUtilTest {

    private JwtUtil jwtUtil(long expirationMs) {
        JwtUtil jwtUtil = new JwtUtil();
        ReflectionTestUtils.setField(jwtUtil, "secret",
                "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
        ReflectionTestUtils.setField(jwtUtil, "expiration", expirationMs);
        return jwtUtil;
    }

    @Test
    void generatedTokenCarriesControlledUserRole() {
        JwtUtil jwtUtil = jwtUtil(60_000);
        String token = jwtUtil.generateToken(UUID.randomUUID(), "alice");

        assertEquals("USER", jwtUtil.getRoleFromToken(token));
    }

    @Test
    void expiredTokenIsRejected() {
        JwtUtil jwtUtil = jwtUtil(-1);
        String token = jwtUtil.generateToken(UUID.randomUUID(), "alice");

        assertThrows(JwtException.class, () -> jwtUtil.validateToken(token, "alice"));
    }
}
