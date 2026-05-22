package com.kinlin.ai.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.dto.ChatRequest;
import com.kinlin.ai.dto.ChatResponse;
import com.kinlin.ai.interceptor.RateLimitInterceptor;
import com.kinlin.ai.interceptor.UserContextInterceptor;
import com.kinlin.ai.service.ChatService;
import com.kinlin.ai.util.JwtUtil;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.jpa.mapping.JpaMetamodelMappingContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * ChatController集成测试
 */
@WebMvcTest(ChatController.class)
@AutoConfigureMockMvc(addFilters = false)
class ChatControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ChatService chatService;

    @MockBean
    private RateLimitInterceptor rateLimitInterceptor;

    @MockBean
    private UserContextInterceptor userContextInterceptor;

    @MockBean
    private JwtUtil jwtUtil;

    @MockBean
    private JpaMetamodelMappingContext jpaMetamodelMappingContext;

    @Autowired
    private ObjectMapper objectMapper;

    @BeforeEach
    void setUp() throws Exception {
        when(rateLimitInterceptor.preHandle(any(), any(), any())).thenReturn(true);
        when(userContextInterceptor.preHandle(any(), any(), any())).thenReturn(true);
    }

    @Test
    void testSendMessage() throws Exception {
        // Given
        ChatRequest request = new ChatRequest();
        request.setText("测试消息");
        request.setRoleId(UUID.randomUUID());

        ChatResponse response = new ChatResponse();
        response.setText("AI回复");
        response.setContextId(UUID.randomUUID().toString());
        response.setConfidence(0.95);

        when(chatService.sendMessage(any(ChatRequest.class), any(UUID.class)))
                .thenReturn(response);

        // When & Then
        mockMvc.perform(post("/chat/text")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("X-User-Id", UUID.randomUUID().toString())
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("AI回复"))
                .andExpect(jsonPath("$.confidence").value(0.95));
    }

    @Test
    void testSendMessage_WithoutUserId() throws Exception {
        // Given
        ChatRequest request = new ChatRequest();
        request.setText("测试消息");

        ChatResponse response = new ChatResponse();
        response.setText("AI回复");

        when(chatService.sendMessage(any(ChatRequest.class), any()))
                .thenReturn(response);

        // When & Then
        mockMvc.perform(post("/chat/text")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());
    }
}

