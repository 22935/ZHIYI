package com.kinlin.ai.dto.agent;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * Lawyer agent chat request DTO.
 */
@Data
public class AgentChatRequest {

    @NotBlank(message = "text cannot be empty")
    private String text;

    @JsonAlias("session_id")
    private String sessionId;
}

