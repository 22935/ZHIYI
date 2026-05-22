package com.kinlin.ai.integration;

import com.kinlin.ai.KinlinAiApplication;
import com.kinlin.ai.dto.ChatRequest;
import com.kinlin.ai.dto.ChatResponse;
import com.kinlin.ai.entity.Role;
import com.kinlin.ai.repository.RoleRepository;
import com.kinlin.ai.util.JwtUtil;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.when;

/**
 * 对话功能集成测试
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class ChatIntegrationTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private RoleRepository roleRepository;

    @MockBean
    private JwtUtil jwtUtil;

    private String baseUrl;
    private UUID userId;
    private UUID roleId;
    private String token;

    @BeforeEach
    void setUp() {
        baseUrl = "http://localhost:" + port + "/chat/text";
        userId = UUID.randomUUID();
        token = "test-token";
        when(jwtUtil.getUsernameFromToken(token)).thenReturn("test-user");
        when(jwtUtil.getUserIdFromToken(token)).thenReturn(userId);
        when(jwtUtil.validateToken(token, "test-user")).thenReturn(true);

        // 创建测试角色
        Role role = new Role();
        role.setName("测试角色");
        role.setRoleType(Role.RoleType.BUILTIN);
        role.setSystemPrompt("你是一个测试角色");
        role = roleRepository.save(role);
        roleId = role.getId();
    }

    @Test
    void testChatFlow() {
        // 1. 发送第一条消息
        ChatRequest request = new ChatRequest();
        request.setText("你好");
        request.setRoleId(roleId);

        HttpHeaders headers = new HttpHeaders();
        headers.set("X-User-Id", userId.toString());
        headers.setBearerAuth(token);
        HttpEntity<ChatRequest> entity = new HttpEntity<>(request, headers);

        ResponseEntity<ChatResponse> response = restTemplate.exchange(
                baseUrl,
                HttpMethod.POST,
                entity,
                ChatResponse.class
        );

        assertTrue(response.getStatusCode().is2xxSuccessful());
        assertNotNull(response.getBody());
        assertNotNull(response.getBody().getContextId());

        String contextId = response.getBody().getContextId();

        // 2. 发送第二条消息（使用相同的contextId）
        request = new ChatRequest();
        request.setText("继续对话");
        request.setRoleId(roleId);
        request.setContextId(contextId);

        entity = new HttpEntity<>(request, headers);
        response = restTemplate.exchange(
                baseUrl,
                HttpMethod.POST,
                entity,
                ChatResponse.class
        );

        assertTrue(response.getStatusCode().is2xxSuccessful());
        assertEquals(contextId, response.getBody().getContextId());
    }
}

