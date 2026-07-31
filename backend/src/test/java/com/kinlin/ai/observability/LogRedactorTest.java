package com.kinlin.ai.observability;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LogRedactorTest {

    @Test
    void removesJwtApiKeyPasswordAndAuthorizationValues() {
        String jwt = "eyJ" + "header.payload.signature";
        String apiKey = "sk" + "-private-model-key";
        String message = "Authorization=Bearer " + jwt + " api_key=" + apiKey + " password=private-password";

        String redacted = LogRedactor.redact(message);

        assertFalse(redacted.contains("header.payload.signature"));
        assertFalse(redacted.contains("private-model-key"));
        assertFalse(redacted.contains("private-password"));
        assertTrue(redacted.contains("[REDACTED]"));
    }
}
