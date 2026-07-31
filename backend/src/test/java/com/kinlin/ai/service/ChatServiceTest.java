package com.kinlin.ai.service;

import com.kinlin.ai.dto.ChatRequest;
import com.kinlin.ai.dto.ChatResponse;
import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.quality.Strictness;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * ChatService单元测试
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class ChatServiceTest {

    @Mock
    private ConversationRepository conversationRepository;

    @Mock
    private MessageRepository messageRepository;

    @Mock
    private AiService aiService;

    @InjectMocks
    private ChatService chatService;

    private ChatRequest chatRequest;
    private UUID userId;
    private UUID roleId;

    @BeforeEach
    void setUp() {
        userId = UUID.randomUUID();
        roleId = UUID.randomUUID();

        chatRequest = new ChatRequest();
        chatRequest.setText("测试消息");
        chatRequest.setRoleId(roleId);
    }

    @Test
    void testSendMessage_NewConversation() {
        // Given
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());
        conversation.setContextId(UUID.randomUUID().toString());
        conversation.setUserId(userId);
        conversation.setRoleId(roleId);

        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");
        aiResponse.setConfidence(0.95);

        when(conversationRepository.findByContextId(anyString())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenReturn(conversation);
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(any(UUID.class)))
                .thenReturn(Collections.emptyList());
        when(aiService.sendTextMessage(anyString(), anyString(), anyList(), anyString()))
                .thenReturn(aiResponse);

        // When
        ChatResponse response = chatService.sendMessage(chatRequest, userId);

        // Then
        assertNotNull(response);
        assertEquals("AI回复", response.getText());
        assertEquals(conversation.getContextId(), response.getContextId());
        verify(messageRepository, times(2)).save(any(Message.class));
    }

    @Test
    void testSendMessage_ExistingConversation() {
        // Given
        String contextId = UUID.randomUUID().toString();
        chatRequest.setContextId(contextId);

        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());
        conversation.setContextId(contextId);

        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");

        when(conversationRepository.findByContextId(contextId))
                .thenReturn(Optional.of(conversation));
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(any(UUID.class)))
                .thenReturn(Collections.emptyList());
        when(aiService.sendTextMessage(anyString(), anyString(), anyList(), anyString()))
                .thenReturn(aiResponse);

        // When
        ChatResponse response = chatService.sendMessage(chatRequest, userId);

        // Then
        assertNotNull(response);
        verify(conversationRepository, never()).save(any(Conversation.class));
    }

    @Test
    void testGetHistory() {
        // Given
        String contextId = UUID.randomUUID().toString();
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());

        Message message = new Message();
        message.setContent("测试消息");

        when(conversationRepository.findByContextId(contextId))
                .thenReturn(Optional.of(conversation));
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId()))
                .thenReturn(List.of(message));

        // When
        List<Message> history = chatService.getHistory(contextId);

        // Then
        assertNotNull(history);
        assertEquals(1, history.size());
        assertEquals("测试消息", history.get(0).getContent());
    }

    @Test
    void testClearHistory() {
        // Given
        String contextId = UUID.randomUUID().toString();
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());

        Message message = new Message();
        message.setContent("测试消息");

        when(conversationRepository.findByContextId(contextId))
                .thenReturn(Optional.of(conversation));
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId()))
                .thenReturn(List.of(message));

        // When
        chatService.clearHistory(contextId);

        // Then
        verify(messageRepository).deleteAll(anyList());
        verify(conversationRepository).delete(conversation);
    }

    @Test
    void testSendMessage_EmptyText() {
        // Given
        chatRequest.setText("");
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());
        conversation.setContextId(UUID.randomUUID().toString());

        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");

        when(conversationRepository.findByContextId(anyString())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenReturn(conversation);
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(any(UUID.class)))
                .thenReturn(Collections.emptyList());
        when(aiService.sendTextMessage(anyString(), anyString(), anyList(), anyString()))
                .thenReturn(aiResponse);

        // When
        ChatResponse response = chatService.sendMessage(chatRequest, userId);

        // Then
        assertNotNull(response);
        verify(aiService).sendTextMessage(eq(""), anyString(), anyList(), anyString());
    }

    @Test
    void testSendMessage_VeryLongText() {
        // Given
        String longText = "测试".repeat(1000); // 2000字符
        chatRequest.setText(longText);
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());
        conversation.setContextId(UUID.randomUUID().toString());

        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");

        when(conversationRepository.findByContextId(anyString())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenReturn(conversation);
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(any(UUID.class)))
                .thenReturn(Collections.emptyList());
        when(aiService.sendTextMessage(anyString(), anyString(), anyList(), anyString()))
                .thenReturn(aiResponse);

        // When
        ChatResponse response = chatService.sendMessage(chatRequest, userId);

        // Then
        assertNotNull(response);
        verify(aiService).sendTextMessage(eq(longText), anyString(), anyList(), anyString());
    }

    @Test
    void testSendMessage_SpecialCharacters() {
        // Given
        chatRequest.setText("测试特殊字符：!@#$%^&*()_+-=[]{}|;':\",./<>?");
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());
        conversation.setContextId(UUID.randomUUID().toString());

        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");

        when(conversationRepository.findByContextId(anyString())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenReturn(conversation);
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(any(UUID.class)))
                .thenReturn(Collections.emptyList());
        when(aiService.sendTextMessage(anyString(), anyString(), anyList(), anyString()))
                .thenReturn(aiResponse);

        // When
        ChatResponse response = chatService.sendMessage(chatRequest, userId);

        // Then
        assertNotNull(response);
    }

    @Test
    void testGetHistory_EmptyHistory() {
        // Given
        String contextId = UUID.randomUUID().toString();
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());

        when(conversationRepository.findByContextId(contextId))
                .thenReturn(Optional.of(conversation));
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId()))
                .thenReturn(Collections.emptyList());

        // When
        List<Message> history = chatService.getHistory(contextId);

        // Then
        assertNotNull(history);
        assertTrue(history.isEmpty());
    }

    @Test
    void testGetHistory_ConversationNotFound() {
        // Given
        String contextId = UUID.randomUUID().toString();

        when(conversationRepository.findByContextId(contextId))
                .thenReturn(Optional.empty());

        // When
        List<Message> history = chatService.getHistory(contextId);

        // Then
        assertNotNull(history);
        assertTrue(history.isEmpty());
    }

    @Test
    void testSendMessage_WithHistory() {
        // Given
        String contextId = UUID.randomUUID().toString();
        chatRequest.setContextId(contextId);

        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());
        conversation.setContextId(contextId);

        Message previousMessage = new Message();
        previousMessage.setContent("之前的消息");
        previousMessage.setRole(Message.MessageRole.USER);

        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");

        when(conversationRepository.findByContextId(contextId))
                .thenReturn(Optional.of(conversation));
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId()))
                .thenReturn(List.of(previousMessage));
        when(aiService.sendTextMessage(anyString(), anyString(), anyList(), anyString()))
                .thenReturn(aiResponse);

        // When
        ChatResponse response = chatService.sendMessage(chatRequest, userId);

        // Then
        assertNotNull(response);
        verify(aiService).sendTextMessage(anyString(), anyString(), argThat(list -> list.size() > 0), anyString());
    }

    @Test
    void testSendMessage_WithRuntimeModelSettings() {
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID());
        conversation.setContextId(UUID.randomUUID().toString());

        chatRequest.setModel("qwen3-plus");
        chatRequest.setBaseUrl("https://example.com/v1");
        chatRequest.setApiKey("test-key");
        chatRequest.setReasoningEffort("high");
        chatRequest.setToolMode("auto");

        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("指定模型回复");

        when(conversationRepository.save(any(Conversation.class))).thenReturn(conversation);
        when(messageRepository.findByConversationIdOrderByCreatedAtAsc(any(UUID.class)))
                .thenReturn(Collections.emptyList());
        when(aiService.sendTextMessage(
                anyString(), anyString(), anyList(), anyString(),
                anyString(), anyString(), anyString(), anyString(), anyString()
        )).thenReturn(aiResponse);

        ChatResponse response = chatService.sendMessage(chatRequest, userId);

        assertEquals("指定模型回复", response.getText());
        verify(aiService).sendTextMessage(
                anyString(), anyString(), anyList(), anyString(),
                eq("qwen3-plus"), eq("https://example.com/v1"), eq("test-key"), eq("high"), eq("auto")
        );
    }
}

