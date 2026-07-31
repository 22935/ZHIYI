package com.kinlin.ai.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Makes client-supplied identity and service headers invisible to application code. */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class SensitiveIdentityHeaderFilter extends OncePerRequestFilter {

    public static final Set<String> SENSITIVE_HEADERS = Set.of(
            "x-user-id",
            "x-user-role",
            "x-tenant-id",
            "x-organization-id",
            "x-workshop-id",
            "x-internal-service-token"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        filterChain.doFilter(new HttpServletRequestWrapper(request) {
            @Override
            public String getHeader(String name) {
                return isSensitive(name) ? null : super.getHeader(name);
            }

            @Override
            public Enumeration<String> getHeaders(String name) {
                return isSensitive(name) ? Collections.emptyEnumeration() : super.getHeaders(name);
            }

            @Override
            public Enumeration<String> getHeaderNames() {
                List<String> safeNames = Collections.list(super.getHeaderNames()).stream()
                        .filter(name -> !isSensitive(name))
                        .toList();
                return Collections.enumeration(safeNames);
            }
        }, response);
    }

    private boolean isSensitive(String name) {
        return name != null && SENSITIVE_HEADERS.contains(name.toLowerCase(Locale.ROOT));
    }
}
