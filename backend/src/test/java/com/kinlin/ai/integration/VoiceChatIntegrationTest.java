package com.kinlin.ai.integration;

import com.kinlin.ai.controller.VoiceController;
import com.kinlin.ai.dto.ChatResponse;
import com.kinlin.ai.service.VoiceService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * 语音对话集成测试
 */
@SpringBootTest
@AutoConfigureMockMvc(addFilters = false)
@ActiveProfiles("test")
class VoiceChatIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private VoiceService voiceService;

    @Test
    void testVoiceMessageEndpoint() throws Exception {
        // 准备
        UUID roleId = UUID.randomUUID();
        UUID userId = UUID.randomUUID();
        byte[] audioData = new byte[]{1, 2, 3, 4, 5};
        
        MockMultipartFile audioFile = new MockMultipartFile(
                "audio",
                "test.wav",
                "audio/wav",
                audioData
        );

        ChatResponse mockResponse = new ChatResponse();
        mockResponse.setText("AI回复文本");
        mockResponse.setRecognizedText("识别的用户语音");
        mockResponse.setConfidence(0.9);
        mockResponse.setContextId("test_context_id");

        when(voiceService.processVoiceMessage(
                any(byte[].class),
                any(UUID.class),
                nullable(String.class),
                any(UUID.class)
        )).thenReturn(mockResponse);

        // 执行和验证
        mockMvc.perform(multipart("/voice/chat")
                        .file(audioFile)
                        .param("roleId", roleId.toString())
                        .header("X-User-Id", userId.toString())
                        .contentType(MediaType.MULTIPART_FORM_DATA))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("AI回复文本"))
                .andExpect(jsonPath("$.recognizedText").value("识别的用户语音"))
                .andExpect(jsonPath("$.confidence").value(0.9));
    }

    @Test
    void testTextToSpeechEndpoint() throws Exception {
        // 准备
        String text = "测试文本";
        String voice = "female";
        Double speed = 1.0;
        Double pitch = 1.0;
        byte[] audioData = new byte[]{1, 2, 3, 4, 5};

        when(voiceService.textToSpeech(text, voice, speed, pitch)).thenReturn(audioData);

        // 执行和验证
        String body = String.format(
                "{\"text\":\"%s\",\"voice\":\"%s\",\"speed\":%s,\"pitch\":%s}",
                text,
                voice,
                speed,
                pitch
        );

        mockMvc.perform(MockMvcRequestBuilders.post("/voice/tts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(content().contentType(MediaType.APPLICATION_OCTET_STREAM))
                .andExpect(content().bytes(audioData));
    }
}





