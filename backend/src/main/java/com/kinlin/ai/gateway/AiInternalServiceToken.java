package com.kinlin.ai.gateway;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.Locale;
import java.util.Set;

/** Validated access to the Java-to-Python service credential. */
@Component
@ConfigurationProperties(prefix = "ai.internal")
public class AiInternalServiceToken {

    private static final int MINIMUM_LENGTH = 32;
    private static final Set<String> FORBIDDEN_VALUES = Set.of(
            "changeme", "change-me", "placeholder", "secret", "your-token-here"
    );

    private String token = "";
    private boolean required;

    @PostConstruct
    void validateConfiguration() {
        if (required && !isValid()) {
            throw new IllegalStateException("AI internal service token is missing or invalid");
        }
    }

    public boolean isValid() {
        String normalized = normalizedToken();
        return normalized.length() >= MINIMUM_LENGTH
                && !FORBIDDEN_VALUES.contains(normalized.toLowerCase(Locale.ROOT));
    }

    public String requiredValue() {
        if (!isValid()) {
            throw new IllegalStateException("AI internal service authentication is not configured");
        }
        return normalizedToken();
    }

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }

    public boolean isRequired() {
        return required;
    }

    public void setRequired(boolean required) {
        this.required = required;
    }

    private String normalizedToken() {
        return token == null ? "" : token.trim();
    }
}
