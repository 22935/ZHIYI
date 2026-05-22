package com.kinlin.ai.service;

import com.kinlin.ai.dto.DigitalHumanRequest;
import com.kinlin.ai.dto.DigitalHumanResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.core.ParameterizedTypeReference;
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
 * DigitalHumanService单元测试
 */
@ExtendWith(MockitoExtension.class)
class DigitalHumanServiceTest {

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

    private DigitalHumanService digitalHumanService;

    @BeforeEach
    void setUp() {
        when(webClientBuilder.baseUrl(anyString())).thenReturn(webClientBuilder);
        when(webClientBuilder.build()).thenReturn(webClient);
        digitalHumanService = new DigitalHumanService(webClientBuilder, "http://localhost:8000", 5000);
        ReflectionTestUtils.setField(digitalHumanService, "aiServiceUrl", "http://localhost:8000");
        ReflectionTestUtils.setField(digitalHumanService, "timeout", 5000);
    }

    @Test
    void testCreateDigitalHuman_Success() {
        // Arrange
        DigitalHumanRequest request = new DigitalHumanRequest();
        request.setRoleId("role1");
        request.setStyle("realistic");

        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("avatar_id", "avatar1"));

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.onStatus(any(), any())).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(any(ParameterizedTypeReference.class))).thenReturn(Mono.just(responseData));

        // Act
        DigitalHumanResponse response = digitalHumanService.createDigitalHuman(request);

        // Assert
        assertNotNull(response);
        assertTrue(response.getSuccess());
        assertNotNull(response.getData());
    }

    @Test
    void testCreateDigitalHuman_Failure() {
        // Arrange
        DigitalHumanRequest request = new DigitalHumanRequest();
        request.setRoleId("role1");

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.onStatus(any(), any())).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(any(ParameterizedTypeReference.class)))
                .thenReturn(Mono.error(new RuntimeException("Service error")));

        // Act
        DigitalHumanResponse response = digitalHumanService.createDigitalHuman(request);

        // Assert
        assertNotNull(response);
        assertFalse(response.getSuccess());
        assertNotNull(response.getMessage());
    }
}

