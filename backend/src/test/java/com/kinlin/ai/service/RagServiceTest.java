package com.kinlin.ai.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * RagService单元测试
 */
@ExtendWith(MockitoExtension.class)
class RagServiceTest {

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

    private RagService ragService;

    private String aiServiceUrl;

    @BeforeEach
    void setUp() {
        aiServiceUrl = "http://localhost:8000";
        when(webClientBuilder.baseUrl(anyString())).thenReturn(webClientBuilder);
        when(webClientBuilder.build()).thenReturn(webClient);
        ragService = new RagService(webClientBuilder, aiServiceUrl);
    }

    @Test
    void testQuery_Success() {
        // Given
        String query = "测试查询";
        Integer topK = 5;
        String contextId = "context-123";

        RagService.RagResponse expectedResponse = new RagService.RagResponse(
                "这是回答",
                List.of(Map.of("doc_id", "doc1", "filename", "test.txt")),
                0.95
        );

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(RagService.RagResponse.class))
                .thenReturn(Mono.just(expectedResponse));

        // When
        RagService.RagResponse result = ragService.query(query, topK, contextId);

        // Then
        assertNotNull(result);
        assertEquals("这是回答", result.answer());
        assertEquals(0.95, result.confidence());
        assertFalse(result.sources().isEmpty());
        verify(webClient).post();
    }

    @Test
    void testQuery_WithNullTopK() {
        // Given
        String query = "测试查询";
        RagService.RagResponse expectedResponse = new RagService.RagResponse(
                "回答",
                List.of(),
                0.9
        );

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(RagService.RagResponse.class))
                .thenReturn(Mono.just(expectedResponse));

        // When
        RagService.RagResponse result = ragService.query(query, null, null);

        // Then
        assertNotNull(result);
    }

    @Test
    void testQuery_Exception() {
        // Given
        String query = "测试查询";

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(RagService.RagResponse.class))
                .thenReturn(Mono.error(new RuntimeException("网络错误")));

        // When
        RagService.RagResponse result = ragService.query(query, 5, null);

        // Then
        assertNotNull(result);
        assertEquals(0.0, result.confidence());
    }

    @Test
    void testListDocuments_Success() {
        // Given
        Map<String, Object> expectedResponse = new HashMap<>();
        expectedResponse.put("documents", List.of());
        expectedResponse.put("count", 0);

        WebClient.RequestHeadersUriSpec requestHeadersUriSpec = mock(WebClient.RequestHeadersUriSpec.class);
        when(webClient.get()).thenReturn(requestHeadersUriSpec);
        doReturn(requestBodySpec).when(requestHeadersUriSpec).uri(any(Function.class));
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class))
                .thenReturn(Mono.just(expectedResponse));

        // When
        Map<String, Object> result = ragService.listDocuments();

        // Then
        assertNotNull(result);
        assertTrue(result.containsKey("documents"));
        assertTrue(result.containsKey("count"));
    }

    @Test
    void testDeleteDocument_Success() {
        // Given
        String docId = "doc-123";
        Map<String, Object> expectedResponse = new HashMap<>();
        expectedResponse.put("message", "删除成功");

        WebClient.RequestHeadersUriSpec requestHeadersUriSpec = mock(WebClient.RequestHeadersUriSpec.class);
        when(webClient.delete()).thenReturn(requestHeadersUriSpec);
        doReturn(requestBodySpec).when(requestHeadersUriSpec).uri(anyString());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class))
                .thenReturn(Mono.just(expectedResponse));

        // When & Then
        assertDoesNotThrow(() -> {
            ragService.deleteDocument(docId);
        });
    }
}

