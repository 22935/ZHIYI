package com.kinlin.ai.service;

import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ConversationServiceTest {

    @Mock
    private ConversationRepository conversationRepository;

    @Mock
    private MessageRepository messageRepository;

    @InjectMocks
    private ConversationService conversationService;

    @Test
    void deleteConversationRemovesOwnedMessagesBeforeConversation() {
        UUID userId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        Conversation conversation = conversation(conversationId, userId);
        when(conversationRepository.findById(conversationId)).thenReturn(Optional.of(conversation));

        assertTrue(conversationService.deleteConversation(conversationId, userId));

        InOrder deletionOrder = inOrder(messageRepository, conversationRepository);
        deletionOrder.verify(messageRepository).deleteByConversationId(conversationId);
        deletionOrder.verify(conversationRepository).delete(conversation);
    }

    @Test
    void deleteConversationRejectsAnotherUsersConversation() {
        UUID ownerId = UUID.randomUUID();
        UUID requesterId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        Conversation conversation = conversation(conversationId, ownerId);
        when(conversationRepository.findById(conversationId)).thenReturn(Optional.of(conversation));

        assertFalse(conversationService.deleteConversation(conversationId, requesterId));

        verify(messageRepository, never()).deleteByConversationId(conversationId);
        verify(conversationRepository, never()).delete(conversation);
    }

    @Test
    void deleteConversationReturnsFalseWhenConversationDoesNotExist() {
        UUID conversationId = UUID.randomUUID();
        when(conversationRepository.findById(conversationId)).thenReturn(Optional.empty());

        assertFalse(conversationService.deleteConversation(conversationId, UUID.randomUUID()));

        verify(messageRepository, never()).deleteByConversationId(conversationId);
    }

    private Conversation conversation(UUID conversationId, UUID userId) {
        Conversation conversation = new Conversation();
        conversation.setId(conversationId);
        conversation.setUserId(userId);
        return conversation;
    }
}
