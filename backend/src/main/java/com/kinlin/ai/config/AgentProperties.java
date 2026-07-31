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
        private String lawyerChatUrl = "http://localhost:8000/ai/agent/lawyer/chat";
        private String teacherChatUrl = "http://localhost:8000/ai/agent/teacher/chat";
        private String programmerChatUrl = "http://localhost:8000/ai/agent/programmer/chat";
        private String writerChatUrl = "http://localhost:8000/ai/agent/writer/chat";
    }
}
