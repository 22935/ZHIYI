package com.kinlin.ai.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * PasswordUtil单元测试
 */
class PasswordUtilTest {

    @Test
    void testEncode_Success() {
        // Given
        String rawPassword = "testpassword123";

        // When
        String encoded = PasswordUtil.encode(rawPassword);

        // Then
        assertNotNull(encoded);
        assertNotEquals(rawPassword, encoded);
        assertTrue(encoded.length() > 0);
    }

    @Test
    void testEncode_DifferentPasswords() {
        // Given
        String password1 = "password1";
        String password2 = "password2";

        // When
        String encoded1 = PasswordUtil.encode(password1);
        String encoded2 = PasswordUtil.encode(password2);

        // Then
        assertNotEquals(encoded1, encoded2);
    }

    @Test
    void testEncode_SamePasswordDifferentHash() {
        // Given
        String password = "samepassword";

        // When
        String encoded1 = PasswordUtil.encode(password);
        String encoded2 = PasswordUtil.encode(password);

        // Then
        // BCrypt每次加密结果不同（因为salt不同），但都能验证通过
        assertNotEquals(encoded1, encoded2);
        assertTrue(PasswordUtil.matches(password, encoded1));
        assertTrue(PasswordUtil.matches(password, encoded2));
    }

    @Test
    void testEncode_EmptyPassword() {
        // When & Then
        assertThrows(IllegalArgumentException.class, () -> {
            PasswordUtil.encode("");
        });
    }

    @Test
    void testEncode_NullPassword() {
        // When & Then
        assertThrows(IllegalArgumentException.class, () -> {
            PasswordUtil.encode(null);
        });
    }

    @Test
    void testMatches_Success() {
        // Given
        String rawPassword = "testpassword123";
        String encoded = PasswordUtil.encode(rawPassword);

        // When
        boolean result = PasswordUtil.matches(rawPassword, encoded);

        // Then
        assertTrue(result);
    }

    @Test
    void testMatches_WrongPassword() {
        // Given
        String rawPassword = "testpassword123";
        String encoded = PasswordUtil.encode(rawPassword);

        // When
        boolean result = PasswordUtil.matches("wrongpassword", encoded);

        // Then
        assertFalse(result);
    }

    @Test
    void testMatches_NullPassword() {
        // Given
        String encoded = PasswordUtil.encode("testpassword");

        // When
        boolean result = PasswordUtil.matches(null, encoded);

        // Then
        assertFalse(result);
    }

    @Test
    void testMatches_NullEncoded() {
        // Given
        String rawPassword = "testpassword";

        // When
        boolean result = PasswordUtil.matches(rawPassword, null);

        // Then
        assertFalse(result);
    }

    @Test
    void testMatches_BothNull() {
        // When
        boolean result = PasswordUtil.matches(null, null);

        // Then
        assertFalse(result);
    }

}

