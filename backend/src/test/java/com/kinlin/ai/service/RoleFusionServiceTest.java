package com.kinlin.ai.service;

import com.kinlin.ai.dto.RoleFusionRequest;
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
 * RoleFusionService单元测试
 */
@ExtendWith(MockitoExtension.class)
class RoleFusionServiceTest {

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

    private RoleFusionService roleFusionService;

    @BeforeEach
    void setUp() {
        when(webClientBuilder.baseUrl(anyString())).thenReturn(webClientBuilder);
        when(webClientBuilder.build()).thenReturn(webClient);
        roleFusionService = new RoleFusionService(webClientBuilder, "http://localhost:8000", 5000);
        ReflectionTestUtils.setField(roleFusionService, "aiServiceUrl", "http://localhost:8000");
        ReflectionTestUtils.setField(roleFusionService, "timeout", 5000);
    }

    @Test
    void testFuseRoles_Success() {
        // Arrange
        RoleFusionRequest request = new RoleFusionRequest();
        request.setQuestion("我想创业");
        
        RoleFusionRequest.RoleInfo role1 = new RoleFusionRequest.RoleInfo();
        role1.setRoleId("lawyer");
        role1.setKnowledgeDomain(Arrays.asList("法律", "合同"));
        
        RoleFusionRequest.RoleInfo role2 = new RoleFusionRequest.RoleInfo();
        role2.setRoleId("business");
        role2.setKnowledgeDomain(Arrays.asList("商业", "策略"));
        
        request.setAvailableRoles(Arrays.asList(role1, role2));
        request.setRoleResponses(Map.of(
            "lawyer", "法律建议...",
            "business", "商业建议..."
        ));

        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("fused_response", "综合建议..."));

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(responseData));

        // Act
        Map<String, Object> result = roleFusionService.fuseRoles(request);

        // Assert
        assertNotNull(result);
    }

    @Test
    void testCalculateRoleWeights_Success() {
        // Arrange
        String question = "我想创业";
        List<RoleFusionRequest.RoleInfo> roles = new ArrayList<>();
        
        RoleFusionRequest.RoleInfo role1 = new RoleFusionRequest.RoleInfo();
        role1.setRoleId("lawyer");
        role1.setKnowledgeDomain(Arrays.asList("法律"));
        roles.add(role1);

        Map<String, Object> responseData = new HashMap<>();
        responseData.put("success", true);
        responseData.put("data", Map.of("weights", Map.of("lawyer", 0.8)));

        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        doReturn(requestBodySpec).when(requestBodySpec).bodyValue(any());
        when(requestBodySpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(Map.class)).thenReturn(Mono.just(responseData));

        // Act
        Map<String, Object> result = roleFusionService.calculateRoleWeights(question, roles);

        // Assert
        assertNotNull(result);
    }
}

