package com.kinlin.ai.controller;

import com.kinlin.ai.dto.agent.AgentChatRequest;
import com.kinlin.ai.dto.agent.AgentChatResponse;
import com.kinlin.ai.service.AgentGatewayService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Agent controller.
 */
@RestController
@RequestMapping({"/api/agent", "/agent"})
@RequiredArgsConstructor
public class AgentController {

    private final AgentGatewayService agentGatewayService;

    @PostMapping("/lawyer/chat")
    public ResponseEntity<AgentChatResponse> lawyerChat(@Valid @RequestBody AgentChatRequest request) {
        AgentChatResponse response = agentGatewayService.chatWithLawyerAgent(request);
        return ResponseEntity.ok(response);
    }
}
