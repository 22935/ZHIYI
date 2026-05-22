package com.kinlin.ai.controller;

import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.security.AuthenticatedUser;
import com.kinlin.ai.service.ConversationService;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 对话会话控制器
 */
@RestController
@RequestMapping("/conversations")
@RequiredArgsConstructor
public class ConversationController {

    private final ConversationService conversationService;

    /**
     * 获取用户的对话列表
     */
    @GetMapping
    public ResponseEntity<List<Conversation>> getUserConversations(
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        userId = resolveUserId(userId);
        if (userId == null) {
            return ResponseEntity.badRequest().build();
        }
        List<Conversation> conversations = conversationService.getUserConversations(userId);
        return ResponseEntity.ok(conversations);
    }

    /**
     * 获取对话详情
     */
    @GetMapping("/{contextId}")
    public ResponseEntity<Conversation> getConversation(@PathVariable String contextId) {
        return conversationService.getConversationByContextId(contextId)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * 删除对话
     */
    @DeleteMapping("/{conversationId}")
    public ResponseEntity<Void> deleteConversation(@PathVariable UUID conversationId) {
        conversationService.deleteConversation(conversationId);
        return ResponseEntity.ok().build();
    }

    /**
     * 更新对话标题
     */
    @PutMapping("/{conversationId}/title")
    public ResponseEntity<Conversation> updateTitle(
            @PathVariable UUID conversationId,
            @RequestBody UpdateTitleRequest request
    ) {
        Conversation conversation = conversationService.updateTitle(conversationId, request.getTitle());
        return ResponseEntity.ok(conversation);
    }

    /**
     * 获取对话详情（包含预览内容）
     */
    @GetMapping("/{conversationId}/detail")
    public ResponseEntity<Map<String, Object>> getConversationDetail(@PathVariable UUID conversationId) {
        Conversation conversation = conversationService.getConversationByContextId("")
                .orElse(null);
        
        // 如果通过contextId找不到，尝试通过ID查找
        if (conversation == null) {
            conversation = conversationService.getConversationById(conversationId)
                    .orElse(null);
        }
        
        if (conversation == null) {
            return ResponseEntity.notFound().build();
        }
        
        // 自动生成标题（如果还没有）
        if (conversation.getTitle() == null || conversation.getTitle().isEmpty()) {
            conversation = conversationService.autoGenerateTitle(conversationId);
        }
        
        String preview = conversationService.getPreviewContent(conversationId);
        
        Map<String, Object> result = new HashMap<>();
        result.put("conversation", conversation);
        result.put("preview", preview);
        
        return ResponseEntity.ok(result);
    }

    /**
     * 清空用户的所有对话
     */
    @DeleteMapping("/all")
    public ResponseEntity<Void> deleteAllConversations(
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        userId = resolveUserId(userId);
        if (userId == null) {
            return ResponseEntity.badRequest().build();
        }
        conversationService.deleteAllConversations(userId);
        return ResponseEntity.ok().build();
    }

    private UUID resolveUserId(UUID userIdHeader) {
        return AuthenticatedUser.currentUserId().orElse(userIdHeader);
    }

    @Data
    static class UpdateTitleRequest {
        private String title;
    }
}

