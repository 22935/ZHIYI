package com.kinlin.ai.controller;

import com.kinlin.ai.entity.Message;
import com.kinlin.ai.repository.MessageRepository;
import com.kinlin.ai.security.AuthenticatedUser;
import com.kinlin.ai.service.ChatService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

/**
 * 搜索控制器
 */
@RestController
@RequestMapping("/search")
@RequiredArgsConstructor
public class SearchController {

    private final ChatService chatService;
    private final MessageRepository messageRepository;

    /**
     * 搜索对话消息
     */
    @GetMapping("/messages")
    public ResponseEntity<List<Message>> searchMessages(
            @RequestParam("keyword") String keyword,
            @RequestParam(value = "contextId", required = false) String contextId,
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        userId = resolveUserId(userId);
        if (contextId != null && !contextId.isEmpty()) {
            List<Message> messages = chatService.getHistory(contextId);
            List<Message> results = messages.stream()
                    .filter(msg -> msg.getContent().toLowerCase().contains(keyword.toLowerCase()))
                    .toList();
            return ResponseEntity.ok(results);
        }
        return ResponseEntity.ok(List.of());
    }

    /**
     * 搜索用户的所有消息
     */
    @GetMapping("/all-messages")
    public ResponseEntity<List<Message>> searchAllMessages(
            @RequestParam("keyword") String keyword,
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        userId = resolveUserId(userId);
        if (userId == null) {
            return ResponseEntity.badRequest().build();
        }

        // 这里需要根据实际需求实现跨对话搜索
        // 简化实现：搜索所有包含关键词的消息
        List<Message> results = messageRepository.findAll().stream()
                .filter(msg -> msg.getContent().toLowerCase().contains(keyword.toLowerCase()))
                .toList();

        return ResponseEntity.ok(results);
    }

    private UUID resolveUserId(UUID userIdHeader) {
        return AuthenticatedUser.currentUserId().orElse(userIdHeader);
    }
}

