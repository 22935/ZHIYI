package com.kinlin.ai.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.dto.RecommendationContextRequest;
import com.kinlin.ai.dto.RecommendationItem;
import com.kinlin.ai.interceptor.RateLimitInterceptor;
import com.kinlin.ai.interceptor.UserContextInterceptor;
import com.kinlin.ai.service.RecommendationService;
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

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RecommendationController.class)
@AutoConfigureMockMvc(addFilters = false)
class RecommendationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private RecommendationService recommendationService;

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
    void getContextualRecommendations_returnsStructuredItems() throws Exception {
        RecommendationContextRequest request = new RecommendationContextRequest();
        request.setRoleName("律师");
        request.setScope("chat");

        RecommendationItem item = new RecommendationItem();
        item.setText("如何保护自己的合法权益？");
        item.setReason("当前处于律师对话场景");
        item.setTargetAction("fill_input");
        item.setConfidence(0.91);
        item.setScope("chat");

        when(recommendationService.generateContextualRecommendations(any(RecommendationContextRequest.class)))
                .thenReturn(List.of(item));

        mockMvc.perform(post("/recommendations/contextual")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].text").value("如何保护自己的合法权益？"))
                .andExpect(jsonPath("$[0].reason").value("当前处于律师对话场景"))
                .andExpect(jsonPath("$[0].targetAction").value("fill_input"))
                .andExpect(jsonPath("$[0].scope").value("chat"));
    }
}
