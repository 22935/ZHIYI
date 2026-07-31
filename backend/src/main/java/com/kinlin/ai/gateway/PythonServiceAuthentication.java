package com.kinlin.ai.gateway;

import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;

/** Applies service authentication in one place for every Java-to-Python client. */
@Component
@RequiredArgsConstructor
public class PythonServiceAuthentication {

    private final AiInternalServiceToken internalServiceToken;

    public void apply(HttpHeaders headers) {
        headers.set(AiGatewayHeaders.INTERNAL_SERVICE_TOKEN, internalServiceToken.requiredValue());
    }
}
