package com.kinlin.ai.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Agent runtime properties.
 */
@Data
@Component
@ConfigurationProperties(prefix = "agent")
public class AgentProperties {

    private boolean enabled = true;

    private int timeoutMs = 240000;

    private int progressTimeoutMs = 5000;

    /** Async preparation should return quickly and must not inherit the sync workflow timeout. */
    private int asyncStartTimeoutMs = 15000;

    private boolean traceEnabled = false;

    private Python python = new Python();

    @Data
    public static class Python {
        private String baseUrl = "http://localhost:8000";
        private String lawyerChatUrl;
        private String teacherChatUrl;
        private String programmerChatUrl;
        private String writerChatUrl;

        public String getLawyerChatUrl() {
            return resolveEndpoint(lawyerChatUrl, "/ai/agent/lawyer/chat");
        }

        public String getTeacherChatUrl() {
            return resolveEndpoint(teacherChatUrl, "/ai/agent/teacher/chat");
        }

        public String getProgrammerChatUrl() {
            return resolveEndpoint(programmerChatUrl, "/ai/agent/programmer/chat");
        }

        public String getWriterChatUrl() {
            return resolveEndpoint(writerChatUrl, "/ai/agent/writer/chat");
        }

        private String resolveEndpoint(String overrideUrl, String path) {
            if (overrideUrl != null && !overrideUrl.isBlank()) {
                return overrideUrl.trim();
            }
            String normalizedBaseUrl = baseUrl == null || baseUrl.isBlank()
                    ? "http://localhost:8000"
                    : baseUrl.trim().replaceAll("/+$", "");
            return normalizedBaseUrl + path;
        }
    }
}
