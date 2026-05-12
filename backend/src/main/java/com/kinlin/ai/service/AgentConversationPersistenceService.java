package com.kinlin.ai.service;

import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Persists agent chat exchanges into the common conversation/message tables
 * so they are visible in the history panel.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentConversationPersistenceService {

    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;

    @Transactional
    public void persistExchange(
            UUID userId,
            String sessionId,
            String userText,
            String assistantText,
            String agentMode
    ) {
        if (userId == null) {
            log.warn("Skip agent conversation persistence because userId is null.");
            return;
        }
        if (sessionId == null || sessionId.isBlank()) {
            log.warn("Skip agent conversation persistence because sessionId is blank.");
            return;
        }
        if (userText == null || userText.isBlank()) {
            log.warn("Skip agent conversation persistence because userText is blank. sessionId={}", sessionId);
            return;
        }

        Conversation conversation = conversationRepository.findByContextId(sessionId)
                .map(existing -> touchConversationOwner(existing, userId))
                .orElseGet(() -> createConversation(userId, sessionId));
        if (conversation == null) {
            return;
        }

        saveMessage(conversation.getId(), Message.MessageRole.USER, userText, agentMode);

        if (assistantText != null && !assistantText.isBlank()) {
            saveMessage(conversation.getId(), Message.MessageRole.ASSISTANT, assistantText, agentMode);
        }
    }

    private Conversation touchConversationOwner(Conversation conversation, UUID userId) {
        if (conversation.getUserId() == null) {
            conversation.setUserId(userId);
        } else if (!conversation.getUserId().equals(userId)) {
            log.warn(
                    "Session {} belongs to another user. Existing={}, incoming={}. Skip persistence to prevent data pollution.",
                    conversation.getContextId(),
                    conversation.getUserId(),
                    userId
            );
            return null;
        }
        conversation.setUpdatedAt(LocalDateTime.now());
        return conversationRepository.save(conversation);
    }

    private Conversation createConversation(UUID userId, String sessionId) {
        Conversation conversation = new Conversation();
        conversation.setUserId(userId);
        conversation.setContextId(sessionId);
        return conversationRepository.save(conversation);
    }

    private void saveMessage(UUID conversationId, Message.MessageRole role, String content, String agentMode) {
        Message message = new Message();
        message.setConversationId(conversationId);
        message.setRole(role);
        message.setContent(content);
        message.setMessageType(Message.MessageType.TEXT);

        Map<String, Object> metadata = new HashMap<>();
        metadata.put("agent_mode", agentMode);
        message.setMetadata(metadata);

        messageRepository.save(message);
    }
}
