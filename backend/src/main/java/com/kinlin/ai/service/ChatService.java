package com.kinlin.ai.service;

import com.kinlin.ai.annotation.LogExecutionTime;
import com.kinlin.ai.dto.ChatRequest;
import com.kinlin.ai.dto.ChatResponse;
import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 对话服务类
 * 处理对话相关的业务逻辑
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ChatService {

    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;
    private final AiService aiService;
    private final RagService ragService;
    private final MetricsService metricsService;
    private final RoleSwitchOptimizer roleSwitchOptimizer;

    /**
     * 发送消息并获取回复
     */
    @Transactional
    @LogExecutionTime("发送消息")
    public ChatResponse sendMessage(ChatRequest request, UUID userId) {
        // 获取或创建对话
        Conversation conversation = getOrCreateConversation(
                request.getContextId(),
                userId,
                request.getRoleId()
        );

        // 保存用户消息
        Message userMessage = new Message();
        userMessage.setConversationId(conversation.getId());
        userMessage.setRole(Message.MessageRole.USER);
        userMessage.setContent(request.getText());
        userMessage.setMessageType(Message.MessageType.TEXT);
        if (request.getFileUrl() != null) {
            userMessage.setFileUrl(request.getFileUrl());
            userMessage.setMessageType(Message.MessageType.IMAGE); // 根据文件类型设置
        }
        messageRepository.save(userMessage);

        // 获取对话上下文：优先使用请求中提供的context，否则从数据库构建
        List<Map<String, String>> context;
        if (request.getContext() != null && !request.getContext().isEmpty()) {
            // 使用前端提供的上下文
            context = request.getContext();
        } else {
            // 从数据库构建上下文
            List<Message> history = messageRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId());
            context = buildContext(history);
        }

        // 可选：使用RAG增强（如果启用）
        String enhancedText = request.getText();
        if (request.getUseRag() != null && request.getUseRag()) {
            try {
                RagService.RagResponse ragResponse = ragService.query(
                        request.getText(),
                        5,  // top_k
                        conversation.getContextId()
                );
                // 将RAG检索结果融入查询
                if (ragResponse != null && ragResponse.sources() != null && !ragResponse.sources().isEmpty()) {
                    enhancedText = request.getText() + "\n\n相关参考信息：" + 
                            ragResponse.sources().stream()
                                    .map(s -> s.get("excerpt") != null ? s.get("excerpt").toString() : "")
                                    .filter(s -> !s.isEmpty())
                                    .limit(3)
                                    .collect(java.util.stream.Collectors.joining("\n"));
                }
            } catch (Exception e) {
                log.warn("RAG增强失败，使用原始查询: " + e.getMessage());
            }
        }

        // 获取角色上下文（使用缓存优化）
        Map<String, Object> roleContext = null;
        if (request.getRoleId() != null) {
            try {
                roleContext = roleSwitchOptimizer.getRoleContext(request.getRoleId());
            } catch (Exception e) {
                log.warn("获取角色上下文失败，使用默认: " + e.getMessage());
            }
        }
        
        // 调用AI服务获取回复
        boolean hasRuntimeModel = request.getModel() != null
                || request.getBaseUrl() != null
                || request.getApiKey() != null
                || request.getToolMode() != null;
        ChatResponse aiResponse;
        if (hasRuntimeModel) {
            aiResponse = aiService.sendTextMessage(
                    enhancedText,
                    request.getRoleId() != null ? request.getRoleId().toString() : null,
                    context,
                    conversation.getContextId(),
                    request.getModel(),
                    request.getBaseUrl(),
                    request.getApiKey(),
                    request.getThinkingMode() != null
                            ? request.getThinkingMode()
                            : request.getReasoningEffort(),
                    request.getToolMode()
            );
        } else {
            aiResponse = aiService.sendTextMessage(
                    enhancedText,
                    request.getRoleId() != null ? request.getRoleId().toString() : null,
                    context,
                    conversation.getContextId()
            );
        }
        
        // 如果角色上下文可用，添加到响应元数据中
        if (roleContext != null) {
            Map<String, Object> responseMetadata = aiResponse.getMetadata() == null
                    ? new HashMap<>()
                    : new HashMap<>(aiResponse.getMetadata());
            responseMetadata.put("role_context", roleContext);
            aiResponse.setMetadata(responseMetadata);
        }

        // 保存AI回复
        Message assistantMessage = new Message();
        assistantMessage.setConversationId(conversation.getId());
        assistantMessage.setRole(Message.MessageRole.ASSISTANT);
        assistantMessage.setContent(aiResponse.getText());
        assistantMessage.setMessageType(Message.MessageType.TEXT);
        Map<String, Object> metadata = new HashMap<>();
        if (aiResponse.getMetadata() != null) {
            metadata.putAll(aiResponse.getMetadata());
        }
        metadata.put("confidence", aiResponse.getConfidence());
        // 添加可解释性信息
        if (aiResponse.getTokensUsed() != null) {
            metadata.put("tokens_used", aiResponse.getTokensUsed());
        }
        if (aiResponse.getSources() != null && !aiResponse.getSources().isEmpty()) {
            metadata.put("sources", aiResponse.getSources());
        }
        if (aiResponse.getReasoningPath() != null) {
            metadata.put("reasoning_path", aiResponse.getReasoningPath());
        }
        assistantMessage.setMetadata(metadata);
        messageRepository.save(assistantMessage);

        // 记录消息数指标
        try {
            metricsService.recordMessageCount();
        } catch (Exception e) {
            log.warn("记录消息指标失败: " + e.getMessage());
        }

        // 缓存清除由 @CacheEvict 注解处理（在 clearHistory 方法中）

        // 设置contextId
        aiResponse.setContextId(conversation.getContextId());

        return aiResponse;
    }

    /**
     * 获取或创建对话
     */
    private Conversation getOrCreateConversation(String contextId, UUID userId, UUID roleId) {
        if (contextId != null && !contextId.isEmpty()) {
            return conversationRepository.findByContextId(contextId)
                    .orElseGet(() -> createNewConversation(userId, roleId));
        }
        return createNewConversation(userId, roleId);
    }

    /**
     * 创建新对话
     */
    private Conversation createNewConversation(UUID userId, UUID roleId) {
        Conversation conversation = new Conversation();
        conversation.setUserId(userId);
        conversation.setRoleId(roleId);
        conversation.setContextId(UUID.randomUUID().toString());
        return conversationRepository.save(conversation);
    }

    /**
     * 构建对话上下文
     */
    private List<Map<String, String>> buildContext(List<Message> messages) {
        return messages.stream()
                .map(msg -> {
                    Map<String, String> contextItem = new HashMap<>();
                    contextItem.put("role", msg.getRole().name().toLowerCase());
                    contextItem.put("content", msg.getContent());
                    if (msg.getFileUrl() != null) {
                        contextItem.put("file_url", msg.getFileUrl());
                    }
                    return contextItem;
                })
                .collect(Collectors.toList());
    }

    /**
     * 获取对话历史
     */
    public List<Message> getHistory(String contextId) {
        return conversationRepository.findByContextId(contextId)
                .map(conversation -> messageRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId()))
                .orElse(Collections.emptyList());
    }

    /**
     * 清除对话历史
     */
    @Transactional
    public void clearHistory(String contextId) {
        conversationRepository.findByContextId(contextId)
                .ifPresent(conversation -> {
                    messageRepository.deleteAll(
                            messageRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId())
                    );
                    conversationRepository.delete(conversation);
                });
    }
}
