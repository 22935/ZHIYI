package com.kinlin.ai.filter;

import com.kinlin.ai.observability.TraceContext;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/** Validates the ingress trace identifier and scopes it to the servlet request. */
public class TraceIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String traceId = TraceContext.acceptedOrNew(singleHeader(request));
        request.setAttribute(TraceContext.REQUEST_ATTRIBUTE, traceId);
        response.setHeader(TraceContext.HEADER, traceId);
        try (MDC.MDCCloseable ignored = MDC.putCloseable(TraceContext.MDC_KEY, traceId)) {
            chain.doFilter(request, response);
        }
    }

    private String singleHeader(HttpServletRequest request) {
        var values = java.util.Collections.list(request.getHeaders(TraceContext.HEADER));
        return values.size() == 1 ? values.get(0) : null;
    }
}
