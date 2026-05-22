package com.kinlin.ai.service;

import com.kinlin.ai.dto.KnowledgeGraphRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

/**
 * KnowledgeGraphService单元测试
 */
@ExtendWith(MockitoExtension.class)
class KnowledgeGraphServiceTest {

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

    @Mock
    private WebClient.RequestHeadersUriSpec requestHeadersUriSpec;

    private KnowledgeGraphService knowledgeGraphService;

    @BeforeEach
    void setUp() {
        when(webClientBuilder.baseUrl(anyString())).thenReturn(webClientBuilder);
        when(webClientBuilder.build()).thenReturn(webClient);
        knowledgeGraphService = new KnowledgeGraphService(webClientBuilder, "http://localhost:8000", 5000);
        ReflectionTestUtils.setField(knowledgeGraphService, "aiServiceUrl", "http://localhost:8000");
        ReflectionTestUtils.setField(knowledgeGraphService, "timeout", 5000);
    }

    @Test
    void testBuildKnowledgeGraph_Success() {
        // Arrange
        List<KnowledgeGraphRequest.DocumentInfo> documents = new ArrayList<>();
        KnowledgeGraphRequest.DocumentInfo doc = new KnowledgeGraphRequest.DocumentInfo();
        doc.setDocId("doc1");
        doc.setText("张三是一名律师");
        documents.add(doc);

        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("entities_count", 10, "triples_count", 20));

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(responseData));

        // Act
        Map<String, Object> result = knowledgeGraphService.buildKnowledgeGraph(documents);

        // Assert
        assertNotNull(result);
    }

    @Test
    void testHybridSearch_Success() {
        // Arrange
        String question = "律师有哪些？";
        List<Map<String, Object>> vectorResults = new ArrayList<>();
        Integer topK = 5;

        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("results", new ArrayList<>()));

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(responseData));

        // Act
        Map<String, Object> result = knowledgeGraphService.hybridSearch(question, vectorResults, topK);

        // Assert
        assertNotNull(result);
    }

    @Test
    void testReasonWithKnowledgeGraph_Success() {
        // Arrange
        String question = "张三和李四的关系是什么？";

        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("reasoning_result", "同事关系"));

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(responseData));

        // Act
        Map<String, Object> result = knowledgeGraphService.reasonWithKnowledgeGraph(question);

        // Assert
        assertNotNull(result);
    }

    @Test
    void testGetGraphStats_Success() {
        // Arrange
        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("entities_count", 10));

        when(webClient.get()).thenReturn(requestHeadersUriSpec);
        doReturn(requestBodySpec).when(requestHeadersUriSpec).uri(anyString());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(responseData));

        // Act
        Map<String, Object> result = knowledgeGraphService.getGraphStats();

        // Assert
        assertNotNull(result);
    }
}

