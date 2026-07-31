package com.kinlin.ai.observability;

import org.slf4j.MDC;

import java.util.UUID;
import java.util.regex.Pattern;

public final class TraceContext {

    public static final String HEADER = "X-Trace-Id";
    public static final String MDC_KEY = "trace_id";
    public static final String REQUEST_ATTRIBUTE = TraceContext.class.getName() + ".traceId";
    private static final Pattern TRACE_PATTERN = Pattern.compile(
            "(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})"
    );

    private TraceContext() { }

    public static boolean isValid(String value) {
        return value != null && value.length() <= 36 && TRACE_PATTERN.matcher(value).matches();
    }

    public static String acceptedOrNew(String candidate) {
        return isValid(candidate) ? candidate : UUID.randomUUID().toString();
    }

    public static String currentTraceId() {
        String value = MDC.get(MDC_KEY);
        return isValid(value) ? value : UUID.randomUUID().toString();
    }
}
