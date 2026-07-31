package com.kinlin.ai.filter;

import com.kinlin.ai.observability.TraceContext;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TraceIdFilterTest {

    private final TraceIdFilter filter = new TraceIdFilter();

    @Test
    void generatesTraceWhenMissingAndClearsMdc() throws Exception {
        MockHttpServletResponse response = invoke(new MockHttpServletRequest());

        assertTrue(TraceContext.isValid(response.getHeader(TraceContext.HEADER)));
        assertNull(MDC.get(TraceContext.MDC_KEY));
    }

    @Test
    void preservesValidTraceAndReplacesInvalidOrDuplicateValues() throws Exception {
        String valid = UUID.randomUUID().toString();
        MockHttpServletRequest validRequest = new MockHttpServletRequest();
        validRequest.addHeader(TraceContext.HEADER, valid);
        assertEquals(valid, invoke(validRequest).getHeader(TraceContext.HEADER));

        MockHttpServletRequest invalidRequest = new MockHttpServletRequest();
        invalidRequest.addHeader(TraceContext.HEADER, "invalid-control-free-value-that-is-too-long");
        assertNotEquals(invalidRequest.getHeader(TraceContext.HEADER),
                invoke(invalidRequest).getHeader(TraceContext.HEADER));

        MockHttpServletRequest duplicateRequest = new MockHttpServletRequest();
        duplicateRequest.addHeader(TraceContext.HEADER, valid);
        duplicateRequest.addHeader(TraceContext.HEADER, UUID.randomUUID().toString());
        assertNotEquals(valid, invoke(duplicateRequest).getHeader(TraceContext.HEADER));
    }

    private MockHttpServletResponse invoke(MockHttpServletRequest request) throws Exception {
        MockHttpServletResponse response = new MockHttpServletResponse();
        filter.doFilter(request, response, new MockFilterChain());
        return response;
    }
}
