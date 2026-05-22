package com.kinlin.ai.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kinlin.ai.dto.LoginRequest;
import com.kinlin.ai.dto.LoginResponse;
import com.kinlin.ai.entity.User;
import com.kinlin.ai.interceptor.RateLimitInterceptor;
import com.kinlin.ai.interceptor.UserContextInterceptor;
import com.kinlin.ai.service.UserService;
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

import java.util.Optional;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * AuthController单元测试
 */
@WebMvcTest(AuthController.class)
@AutoConfigureMockMvc(addFilters = false)
class AuthControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private UserService userService;

    @MockBean
    private JwtUtil jwtUtil;

    @MockBean
    private RateLimitInterceptor rateLimitInterceptor;

    @MockBean
    private UserContextInterceptor userContextInterceptor;

    @MockBean
    private JpaMetamodelMappingContext jpaMetamodelMappingContext;

    @Autowired
    private ObjectMapper objectMapper;

    private User testUser;
    private UUID userId;
    private String username;
    private String password;
    private String token;

    @BeforeEach
    void setUp() throws Exception {
        userId = UUID.randomUUID();
        username = "testuser";
        password = "testpassword123";
        token = "test-jwt-token";

        testUser = new User();
        testUser.setId(userId);
        testUser.setUsername(username);

        when(rateLimitInterceptor.preHandle(any(), any(), any())).thenReturn(true);
        when(userContextInterceptor.preHandle(any(), any(), any())).thenReturn(true);
    }

    @Test
    void testLogin_Success() throws Exception {
        // Given
        LoginRequest request = new LoginRequest();
        request.setUsername(username);
        request.setPassword(password);

        when(userService.validateUser(username, password))
                .thenReturn(Optional.of(testUser));
        when(jwtUtil.generateToken(userId, username)).thenReturn(token);

        // When & Then
        mockMvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").value(token))
                .andExpect(jsonPath("$.userId").value(userId.toString()))
                .andExpect(jsonPath("$.username").value(username))
                .andExpect(jsonPath("$.message").value("登录成功"));
    }

    @Test
    void testLogin_InvalidCredentials() throws Exception {
        // Given
        LoginRequest request = new LoginRequest();
        request.setUsername(username);
        request.setPassword("wrongpassword");

        when(userService.validateUser(username, "wrongpassword"))
                .thenReturn(Optional.empty());

        // When & Then
        mockMvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message").value("用户名或密码错误"));
    }

    @Test
    void testLogin_InvalidRequest() throws Exception {
        // Given
        LoginRequest request = new LoginRequest();
        // 缺少必填字段

        // When & Then
        mockMvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void testRegister_Success() throws Exception {
        // Given
        LoginRequest request = new LoginRequest();
        request.setUsername(username);
        request.setPassword(password);
        request.setEmail("test@example.com");

        when(userService.getUserByUsername(username))
                .thenReturn(Optional.empty());
        when(userService.createUser(username, password, "test@example.com"))
                .thenReturn(testUser);
        when(jwtUtil.generateToken(userId, username)).thenReturn(token);

        // When & Then
        mockMvc.perform(post("/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").value(token))
                .andExpect(jsonPath("$.userId").value(userId.toString()))
                .andExpect(jsonPath("$.username").value(username))
                .andExpect(jsonPath("$.message").value("注册成功"));
    }

    @Test
    void testRegister_UsernameExists() throws Exception {
        // Given
        LoginRequest request = new LoginRequest();
        request.setUsername(username);
        request.setPassword(password);

        when(userService.getUserByUsername(username))
                .thenReturn(Optional.of(testUser));

        // When & Then
        mockMvc.perform(post("/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("用户名已存在"));
    }

    @Test
    void testRegister_EmptyUsername() throws Exception {
        // Given
        LoginRequest request = new LoginRequest();
        request.setUsername("");
        request.setPassword(password);

        // When & Then
        mockMvc.perform(post("/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void testRegister_EmptyPassword() throws Exception {
        // Given
        LoginRequest request = new LoginRequest();
        request.setUsername(username);
        request.setPassword("");

        // When & Then
        mockMvc.perform(post("/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void testRegister_EmailExists() throws Exception {
        // Given
        LoginRequest request = new LoginRequest();
        request.setUsername("newuser");
        request.setPassword(password);
        request.setEmail("existing@example.com");

        when(userService.getUserByUsername("newuser"))
                .thenReturn(Optional.empty());
        when(userService.createUser("newuser", password, "existing@example.com"))
                .thenThrow(new IllegalArgumentException("邮箱已被使用"));

        // When & Then
        mockMvc.perform(post("/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("邮箱已被使用"));
    }
    @Test
    void testVerifyToken_Success() throws Exception {
        when(jwtUtil.getUsernameFromToken(token)).thenReturn(username);
        when(jwtUtil.getUserIdFromToken(token)).thenReturn(userId);
        when(jwtUtil.validateToken(token, username)).thenReturn(true);

        mockMvc.perform(get("/auth/verify")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(true))
                .andExpect(jsonPath("$.userId").value(userId.toString()))
                .andExpect(jsonPath("$.username").value(username));
    }

    @Test
    void testVerifyToken_MissingAuthorization() throws Exception {
        mockMvc.perform(get("/auth/verify"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(false));
    }
}

