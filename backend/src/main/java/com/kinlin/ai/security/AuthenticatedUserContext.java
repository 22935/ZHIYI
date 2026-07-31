package com.kinlin.ai.security;

import java.util.UUID;

/** Immutable identity created only after successful JWT verification. */
public record AuthenticatedUserContext(
        UUID userId,
        String subject,
        String role,
        String tenantId,
        String traceId
) {
}
