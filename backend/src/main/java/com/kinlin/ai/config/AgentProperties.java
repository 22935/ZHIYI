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

    private int timeoutMs = 30000;

    private boolean traceEnabled = false;

    private Python python = new Python();

    @Data
    public static class Python {
        private String lawyerChatUrl = "http://localhost:8000/ai/agent/lawyer/chat";
    }
}

