package com.kinlin.ai.service;

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

import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * VoiceService单元测试
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class VoiceServiceTest {

    @Mock
    private ConversationRepository conversationRepository;

    @Mock
    private MessageRepository messageRepository;

    @Mock
    private AiService aiService;

    @InjectMocks
    private VoiceService voiceService;

    private UUID userId;
    private UUID roleId;
    private byte[] audioData;

    @BeforeEach
    void setUp() {
        userId = UUID.randomUUID();
        roleId = UUID.randomUUID();
        audioData = new byte[]{1, 2, 3, 4, 5};
    }

    @Test
    void testProcessVoiceMessage_NewConversation() {
        // 准备
        String contextId = null;
        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");
        aiResponse.setRecognizedText("识别的文本");
        aiResponse.setConfidence(0.9);

        when(conversationRepository.findByContextId(anyString())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenAnswer(invocation -> {
            Conversation conv = invocation.getArgument(0);
            conv.setId(UUID.randomUUID());
            return conv;
        });
        when(aiService.sendVoiceMessage(any(byte[].class), anyString())).thenReturn(aiResponse);
        when(messageRepository.save(any(Message.class))).thenAnswer(invocation -> invocation.getArgument(0));

        // 执行
        ChatResponse response = voiceService.processVoiceMessage(
                audioData, roleId, contextId, userId
        );

        // 验证
        assertNotNull(response);
        assertEquals("AI回复", response.getText());
        assertEquals("识别的文本", response.getRecognizedText());
        assertNotNull(response.getContextId());
        verify(messageRepository, times(2)).save(any(Message.class)); // 用户消息和AI回复
    }

    @Test
    void testProcessVoiceMessage_ExistingConversation() {
        // 准备
        String contextId = "existing_context_id";
        Conversation existingConv = new Conversation();
        existingConv.setId(UUID.randomUUID());
        existingConv.setContextId(contextId);

        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");
        aiResponse.setRecognizedText("识别的文本");

        when(conversationRepository.findByContextId(contextId)).thenReturn(Optional.of(existingConv));
        when(aiService.sendVoiceMessage(any(byte[].class), anyString())).thenReturn(aiResponse);
        when(messageRepository.save(any(Message.class))).thenAnswer(invocation -> invocation.getArgument(0));

        // 执行
        ChatResponse response = voiceService.processVoiceMessage(
                audioData, roleId, contextId, userId
        );

        // 验证
        assertNotNull(response);
        assertEquals(contextId, response.getContextId());
        verify(conversationRepository, never()).save(any(Conversation.class));
    }

    @Test
    void testTextToSpeech() {
        // 准备
        String text = "测试文本";
        String voice = "female";
        Double speed = 1.0;
        Double pitch = 1.0;
        byte[] expectedAudio = new byte[]{1, 2, 3};

        when(aiService.textToSpeech(text, voice, speed, pitch)).thenReturn(expectedAudio);

        // 执行
        byte[] result = voiceService.textToSpeech(text, voice, speed, pitch);

        // 验证
        assertNotNull(result);
        assertArrayEquals(expectedAudio, result);
        verify(aiService).textToSpeech(text, voice, speed, pitch);
    }

    @Test
    void testProcessVoiceMessage_EmptyAudioData() {
        // 准备
        byte[] emptyAudio = new byte[0];
        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");
        aiResponse.setRecognizedText("");

        when(conversationRepository.findByContextId(anyString())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenAnswer(invocation -> {
            Conversation conv = invocation.getArgument(0);
            conv.setId(UUID.randomUUID());
            return conv;
        });
        when(aiService.sendVoiceMessage(any(byte[].class), anyString())).thenReturn(aiResponse);
        when(messageRepository.save(any(Message.class))).thenAnswer(invocation -> invocation.getArgument(0));

        // 执行
        ChatResponse response = voiceService.processVoiceMessage(
                emptyAudio, roleId, null, userId
        );

        // 验证
        assertNotNull(response);
        verify(aiService).sendVoiceMessage(any(byte[].class), anyString());
    }

    @Test
    void testProcessVoiceMessage_NullContextId() {
        // 准备
        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");
        aiResponse.setRecognizedText("识别的文本");

        when(conversationRepository.findByContextId(anyString())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenAnswer(invocation -> {
            Conversation conv = invocation.getArgument(0);
            conv.setId(UUID.randomUUID());
            return conv;
        });
        when(aiService.sendVoiceMessage(any(byte[].class), anyString())).thenReturn(aiResponse);
        when(messageRepository.save(any(Message.class))).thenAnswer(invocation -> invocation.getArgument(0));

        // 执行
        ChatResponse response = voiceService.processVoiceMessage(
                audioData, roleId, null, userId
        );

        // 验证
        assertNotNull(response);
        assertNotNull(response.getContextId());
    }

    @Test
    void testTextToSpeech_EmptyText() {
        // 准备
        String text = "";
        String voice = "default";
        Double speed = 1.0;
        Double pitch = 1.0;
        byte[] expectedAudio = new byte[0];

        when(aiService.textToSpeech(text, voice, speed, pitch)).thenReturn(expectedAudio);

        // 执行
        byte[] result = voiceService.textToSpeech(text, voice, speed, pitch);

        // 验证
        assertNotNull(result);
        assertArrayEquals(expectedAudio, result);
    }

    @Test
    void testTextToSpeech_DifferentVoices() {
        // 准备
        String text = "测试文本";
        String[] voices = {"default", "female", "male", "gentle", "lively"};
        Double speed = 1.0;
        Double pitch = 1.0;
        byte[] expectedAudio = new byte[]{1, 2, 3};

        for (String voice : voices) {
            when(aiService.textToSpeech(text, voice, speed, pitch)).thenReturn(expectedAudio);

            // 执行
            byte[] result = voiceService.textToSpeech(text, voice, speed, pitch);

            // 验证
            assertNotNull(result);
            assertArrayEquals(expectedAudio, result);
        }
    }

    @Test
    void testTextToSpeech_DifferentSpeedAndPitch() {
        // 准备
        String text = "测试文本";
        String voice = "default";
        Double[] speeds = {0.5, 1.0, 1.5, 2.0};
        Double[] pitches = {0.5, 1.0, 1.5, 2.0};
        byte[] expectedAudio = new byte[]{1, 2, 3};

        for (Double speed : speeds) {
            for (Double pitch : pitches) {
                when(aiService.textToSpeech(text, voice, speed, pitch)).thenReturn(expectedAudio);

                // 执行
                byte[] result = voiceService.textToSpeech(text, voice, speed, pitch);

                // 验证
                assertNotNull(result);
                assertArrayEquals(expectedAudio, result);
            }
        }
    }

    @Test
    void testProcessVoiceMessage_NoRecognizedText() {
        // 准备
        String contextId = null;
        ChatResponse aiResponse = new ChatResponse();
        aiResponse.setText("AI回复");
        // 不设置recognizedText，测试fallback逻辑

        when(conversationRepository.findByContextId(anyString())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenAnswer(invocation -> {
            Conversation conv = invocation.getArgument(0);
            conv.setId(UUID.randomUUID());
            return conv;
        });
        when(aiService.sendVoiceMessage(any(byte[].class), anyString())).thenReturn(aiResponse);
        when(messageRepository.save(any(Message.class))).thenAnswer(invocation -> invocation.getArgument(0));

        // 执行
        ChatResponse response = voiceService.processVoiceMessage(
                audioData, roleId, contextId, userId
        );

        // 验证
        assertNotNull(response);
        assertNotNull(response.getRecognizedText()); // 应该使用text作为fallback
        verify(messageRepository, times(2)).save(any(Message.class));
    }
}





