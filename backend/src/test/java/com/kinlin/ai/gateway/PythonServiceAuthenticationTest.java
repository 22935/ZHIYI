package com.kinlin.ai.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PythonServiceAuthenticationTest {

    @Test
    void appliesValidatedTokenToInternalHeader() {
        AiInternalServiceToken token = new AiInternalServiceToken();
        token.setToken("0123456789abcdef0123456789abcdef");
        PythonServiceAuthentication authentication = new PythonServiceAuthentication(token);
        HttpHeaders headers = new HttpHeaders();

        authentication.apply(headers);

        assertEquals("0123456789abcdef0123456789abcdef",
                headers.getFirst(AiGatewayHeaders.INTERNAL_SERVICE_TOKEN));
    }

    @Test
    void rejectsMissingShortAndPlaceholderTokensWithoutEchoingValues() {
        for (String invalid : new String[]{"", "short", "placeholder"}) {
            AiInternalServiceToken token = new AiInternalServiceToken();
            token.setToken(invalid);

            IllegalStateException error = assertThrows(IllegalStateException.class, token::requiredValue);
            assertEquals("AI internal service authentication is not configured", error.getMessage());
        }
    }
}
