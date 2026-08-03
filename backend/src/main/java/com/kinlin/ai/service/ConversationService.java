package com.kinlin.ai.service;

import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * 对话服务类
 * 处理对话会话相关的业务逻辑
 */
@Service
@RequiredArgsConstructor
public class ConversationService {

    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;

    /**
     * 获取用户的对话列表（包含预览内容）
     */
    @Transactional
    public List<Conversation> getUserConversations(UUID userId) {
        List<Conversation> conversations = conversationRepository.findRecentConversationsByUserId(userId);
        return hydrateConversationPreviews(conversations);
    }

    @Transactional
    public List<Conversation> getUserConversations(UUID userId, String workspaceMode) {
        List<Conversation> conversations = conversationRepository
                .findRecentConversationsByUserIdAndWorkspaceMode(userId, normalizeWorkspaceMode(workspaceMode));
        return hydrateConversationPreviews(conversations);
    }

    private List<Conversation> hydrateConversationPreviews(List<Conversation> conversations) {
        // 为每个对话自动生成标题（如果还没有）
        conversations.forEach(conv -> {
            String preview = getPreviewContent(conv.getId());
            conv.setPreview(preview);
            if (conv.getTitle() == null || conv.getTitle().isEmpty()) {
                try {
                    String title = preview.length() > 30 ? preview.substring(0, 30) + "..." : preview;
                    conv.setTitle(title);
                    conversationRepository.save(conv);
                } catch (Exception e) {
                    // 忽略错误，继续处理
                }
            }
        });
        return conversations;
    }

    private String normalizeWorkspaceMode(String workspaceMode) {
        return "agent".equalsIgnoreCase(workspaceMode) ? "agent" : "chat";
    }

    /**
     * 根据上下文ID获取对话
     */
    public Optional<Conversation> getConversationByContextId(String contextId) {
        return conversationRepository.findByContextId(contextId);
    }

    /**
     * 根据ID获取对话
     */
    public Optional<Conversation> getConversationById(UUID conversationId) {
        return conversationRepository.findById(conversationId);
    }

    /**
     * 创建新对话
     */
    @Transactional
    public Conversation createConversation(UUID userId, UUID roleId) {
        Conversation conversation = new Conversation();
        conversation.setUserId(userId);
        conversation.setRoleId(roleId);
        conversation.setContextId(UUID.randomUUID().toString());
        return conversationRepository.save(conversation);
    }

    /**
     * 删除对话
     */
    @Transactional
    public boolean deleteConversation(UUID conversationId, UUID userId) {
        Optional<Conversation> conversation = conversationRepository.findById(conversationId);
        if (conversation.isEmpty() || !userId.equals(conversation.get().getUserId())) {
            return false;
        }

        messageRepository.deleteByConversationId(conversationId);
        conversationRepository.delete(conversation.get());
        return true;
    }

    /**
     * 获取或创建对话
     */
    @Transactional
    public Conversation getOrCreateConversation(String contextId, UUID userId, UUID roleId) {
        if (contextId != null && !contextId.isEmpty()) {
            return conversationRepository.findByContextId(contextId)
                    .orElseGet(() -> createConversation(userId, roleId));
        }
        return createConversation(userId, roleId);
    }

    /**
     * 更新对话标题
     */
    @Transactional
    public Conversation updateTitle(UUID conversationId, String title) {
        Conversation conversation = conversationRepository.findById(conversationId)
                .orElseThrow(() -> new RuntimeException("对话不存在"));
        conversation.setTitle(title);
        return conversationRepository.save(conversation);
    }

    /**
     * 获取对话预览内容（第一条用户消息的前50个字符）
     */
    public String getPreviewContent(UUID conversationId) {
        List<Message> messages = messageRepository.findByConversationIdOrderByCreatedAtAsc(conversationId);
        if (messages.isEmpty()) {
            return "暂无消息";
        }
        // 查找第一条用户消息
        for (Message message : messages) {
            if (message.getRole() == Message.MessageRole.USER) {
                String content = message.getContent();
                if (content.length() > 50) {
                    return content.substring(0, 50) + "...";
                }
                return content;
            }
        }
        return "暂无预览";
    }

    /**
     * 自动生成对话标题（基于第一条用户消息）
     */
    @Transactional
    public Conversation autoGenerateTitle(UUID conversationId) {
        Conversation conversation = conversationRepository.findById(conversationId)
                .orElseThrow(() -> new RuntimeException("对话不存在"));
        
        // 如果已有标题，不自动生成
        if (conversation.getTitle() != null && !conversation.getTitle().isEmpty()) {
            return conversation;
        }
        
        String preview = getPreviewContent(conversationId);
        // 生成标题（最多30个字符）
        String title = preview.length() > 30 ? preview.substring(0, 30) + "..." : preview;
        conversation.setTitle(title);
        return conversationRepository.save(conversation);
    }

    /**
     * 删除用户的所有对话
     */
    @Transactional
    public void deleteAllConversations(UUID userId) {
        List<Conversation> conversations = conversationRepository.findByUserId(userId);
        deleteConversations(conversations);
    }

    @Transactional
    public void deleteAllConversations(UUID userId, String workspaceMode) {
        List<Conversation> conversations = conversationRepository
                .findRecentConversationsByUserIdAndWorkspaceMode(userId, normalizeWorkspaceMode(workspaceMode));
        deleteConversations(conversations);
    }

    private void deleteConversations(List<Conversation> conversations) {
        // 删除所有相关的消息
        for (Conversation conversation : conversations) {
            List<Message> messages = messageRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId());
            if (!messages.isEmpty()) {
                messageRepository.deleteAll(messages);
            }
        }
        // 删除所有对话
        conversationRepository.deleteAll(conversations);
    }
}

