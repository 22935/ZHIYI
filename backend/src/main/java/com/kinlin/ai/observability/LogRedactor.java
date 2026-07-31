package com.kinlin.ai.observability;

import java.util.List;
import java.util.regex.Pattern;

public final class LogRedactor {

    private static final List<Pattern> SENSITIVE_PATTERNS = List.of(
            Pattern.compile("(?i)(authorization|cookie|x-internal-service-token|api[-_ ]?key|password)\\s*[:=]\\s*[^\\s,;]+"),
            Pattern.compile("(?i)bearer\\s+[A-Za-z0-9._~+/=-]+"),
            Pattern.compile("\\beyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\b"),
            Pattern.compile("\\bsk-[A-Za-z0-9_-]{8,}\\b")
    );

    private LogRedactor() { }

    public static String redact(String value) {
        String result = value == null ? "" : value;
        for (Pattern pattern : SENSITIVE_PATTERNS) {
            result = pattern.matcher(result).replaceAll("[REDACTED]");
        }
        return result;
    }
}
