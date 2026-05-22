package com.kinlin.ai.controller;

import com.kinlin.ai.dto.agent.AgentChatRequest;
import com.kinlin.ai.dto.agent.AgentChatResponse;
import com.kinlin.ai.security.AuthenticatedUser;
import com.kinlin.ai.service.AgentConversationPersistenceService;
import com.kinlin.ai.service.AgentGatewayService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestHeader;

import java.util.UUID;

/**
 * Agent controller.
 */
@Slf4j
@RestController
@RequestMapping({"/api/agent", "/agent"})
@RequiredArgsConstructor
public class AgentController {

    private final AgentGatewayService agentGatewayService;
    private final AgentConversationPersistenceService agentConversationPersistenceService;

    @PostMapping("/lawyer/chat")
    public ResponseEntity<AgentChatResponse> lawyerChat(
            @Valid @RequestBody AgentChatRequest request,
            @RequestHeader(value = "X-User-Id", required = false) UUID userIdHeader
    ) {
        UUID userId = resolveUserId(userIdHeader);
        AgentChatResponse response = agentGatewayService.chatWithLawyerAgent(request);
        persistConversation(userId, request, response, "lawyer");
        return ResponseEntity.ok(response);
    }

    @PostMapping("/teacher/chat")
    public ResponseEntity<AgentChatResponse> teacherChat(
            @Valid @RequestBody AgentChatRequest request,
            @RequestHeader(value = "X-User-Id", required = false) UUID userIdHeader
    ) {
        UUID userId = resolveUserId(userIdHeader);
        AgentChatResponse response = agentGatewayService.chatWithTeacherAgent(request);
        persistConversation(userId, request, response, "teacher");
        return ResponseEntity.ok(response);
    }

    @PostMapping("/programmer/chat")
    public ResponseEntity<AgentChatResponse> programmerChat(
            @Valid @RequestBody AgentChatRequest request,
            @RequestHeader(value = "X-User-Id", required = false) UUID userIdHeader
    ) {
        UUID userId = resolveUserId(userIdHeader);
        AgentChatResponse response = agentGatewayService.chatWithProgrammerAgent(request);
        persistConversation(userId, request, response, "programmer");
        return ResponseEntity.ok(response);
    }

    @PostMapping("/writer/chat")
    public ResponseEntity<AgentChatResponse> writerChat(
            @Valid @RequestBody AgentChatRequest request,
            @RequestHeader(value = "X-User-Id", required = false) UUID userIdHeader
    ) {
        UUID userId = resolveUserId(userIdHeader);
        AgentChatResponse response = agentGatewayService.chatWithWriterAgent(request);
        persistConversation(userId, request, response, "writer");
        return ResponseEntity.ok(response);
    }

    private UUID resolveUserId(UUID userIdHeader) {
        return AuthenticatedUser.currentUserId().orElse(userIdHeader);
    }

    private void persistConversation(UUID userId, AgentChatRequest request, AgentChatResponse response, String agentMode) {
        try {
            if (response == null) {
                return;
            }

            String sessionId = firstNonBlank(
                    response.getSessionId(),
                    request != null ? request.getSessionId() : null,
                    UUID.randomUUID().toString()
            );
            response.setSessionId(sessionId);

            String userText = request != null ? request.getText() : null;
            String assistantText = firstNonBlank(response.getAnswer(), response.getMessage(), response.getError());

            agentConversationPersistenceService.persistExchange(
                    userId,
                    sessionId,
                    userText,
                    assistantText,
                    agentMode
            );
        } catch (Exception e) {
            log.error("Persisting agent conversation failed. mode={}", agentMode, e);
        }
    }

    private String firstNonBlank(String... values) {
        if (values == null) {
            return "";
        }
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return "";
    }
}
