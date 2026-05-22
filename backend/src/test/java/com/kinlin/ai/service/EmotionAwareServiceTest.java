package com.kinlin.ai.service;

import com.kinlin.ai.dto.EmotionAnalyzeRequest;
import com.kinlin.ai.dto.EmotionAwareResponseRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

/**
 * EmotionAwareService单元测试
 */
@ExtendWith(MockitoExtension.class)
class EmotionAwareServiceTest {

    @Mock
    private WebClient.Builder webClientBuilder;

    @Mock
    private WebClient webClient;

    @Mock
    private WebClient.RequestBodyUriSpec requestBodyUriSpec;

    @Mock
    private WebClient.RequestBodySpec requestBodySpec;

    @Mock
    private WebClient.ResponseSpec responseSpec;

    private EmotionAwareService emotionAwareService;

    @BeforeEach
    void setUp() {
        when(webClientBuilder.baseUrl(anyString())).thenReturn(webClientBuilder);
        when(webClientBuilder.build()).thenReturn(webClient);
        emotionAwareService = new EmotionAwareService(webClientBuilder, "http://localhost:8000", 5000);
        ReflectionTestUtils.setField(emotionAwareService, "aiServiceUrl", "http://localhost:8000");
        ReflectionTestUtils.setField(emotionAwareService, "timeout", 5000);
    }

    @Test
    void testAnalyzeEmotion_Success() {
        // Arrange
        EmotionAnalyzeRequest request = new EmotionAnalyzeRequest();
        request.setText("我很开心");

        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("emotion", "happy", "intensity", 0.8));

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(responseData));

        // Act
        Map<String, Object> result = emotionAwareService.analyzeEmotion(request);

        // Assert
        assertNotNull(result);
        assertTrue(result.containsKey("emotion"));
    }

    @Test
    void testAnalyzeEmotion_Failure() {
        // Arrange
        EmotionAnalyzeRequest request = new EmotionAnalyzeRequest();
        request.setText("测试");

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.error(new RuntimeException("Service error")));

        // Act
        Map<String, Object> result = emotionAwareService.analyzeEmotion(request);

        // Assert
        assertNotNull(result);
        assertEquals("neutral", result.get("emotion"));
    }

    @Test
    void testGenerateEmotionAwareResponse_Success() {
        // Arrange
        EmotionAwareResponseRequest request = new EmotionAwareResponseRequest();
        request.setQuestion("你好");
        request.setBaseRole(new HashMap<>());

        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("response", "你好，很高兴见到你"));

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(responseData));

        // Act
        Map<String, Object> result = emotionAwareService.generateEmotionAwareResponse(request);

        // Assert
        assertNotNull(result);
    }
}

