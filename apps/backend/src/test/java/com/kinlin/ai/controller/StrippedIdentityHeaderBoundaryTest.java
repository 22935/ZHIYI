package com.kinlin.ai.controller;

import com.kinlin.ai.filter.SensitiveIdentityHeaderFilter;
import com.kinlin.ai.security.AuthenticatedUserContext;
import com.kinlin.ai.service.ChatQualityService;
import com.kinlin.ai.service.ChatService;
import com.kinlin.ai.service.ConversationService;
import com.kinlin.ai.service.RoleService;
import com.kinlin.ai.service.SearchService;
import com.kinlin.ai.service.UserService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 身份头死参数清理（J1.2B §9）的行为一致性验证：X-User-Id 入站即被
 * {@link SensitiveIdentityHeaderFilter} 剥除，各 controller 的落库/查询身份只来自
 * 认证上下文；伪造 X-User-Id 不产生任何影响（与移除死参数前等价）。
 */
@ExtendWith(MockitoExtension.class)
class StrippedIdentityHeaderBoundaryTest {

    private static final String FORGED = "11111111-1111-1111-1111-111111111111";

    @Mock private ChatService chatService;
    @Mock private SearchService searchService;
    @Mock private ConversationService conversationService;
    @Mock private RoleService roleService;
    @Mock private UserService userService;
    @Mock private ChatQualityService qualityService;

    private UUID authenticatedUserId;

    @BeforeEach
    void setUp() {
        authenticatedUserId = UUID.randomUUID();
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void chatHistoryIdentityComesOnlyFromTheAuthenticatedContext() throws Exception {
        when(chatService.getHistory(anyString(), any(UUID.class))).thenReturn(List.of());

        withAuth(new ChatController(chatService))
                .perform(get("/chat/history/{contextId}", "c1").header("X-User-Id", FORGED))
                .andExpect(status().isOk());

        ArgumentCaptor<UUID> userId = ArgumentCaptor.forClass(UUID.class);
        verify(chatService).getHistory(anyString(), userId.capture());
        assertEquals(authenticatedUserId, userId.getValue(), "伪造头不得影响会话属主判定");
    }

    @Test
    void searchIdentityComesOnlyFromTheAuthenticatedContext() throws Exception {
        when(searchService.searchMessages(any(UUID.class), anyString())).thenReturn(List.of());

        withAuth(new SearchController(chatService, searchService))
                .perform(get("/search/all-messages").param("keyword", "x").header("X-User-Id", FORGED))
                .andExpect(status().isOk());

        ArgumentCaptor<UUID> userId = ArgumentCaptor.forClass(UUID.class);
        verify(searchService).searchMessages(userId.capture(), anyString());
        assertEquals(authenticatedUserId, userId.getValue());
    }

    @Test
    void withoutAuthenticationSearchStaysRejectedInsteadOfTrustingTheHeader() throws Exception {
        withoutAuth(new SearchController(chatService, searchService))
                .perform(get("/search/all-messages").param("keyword", "x").header("X-User-Id", FORGED))
                .andExpect(status().isBadRequest());
    }

    @Test
    void conversationListIdentityComesOnlyFromTheAuthenticatedContext() throws Exception {
        when(conversationService.getUserConversations(any(UUID.class))).thenReturn(List.of());

        withAuth(new ConversationController(conversationService))
                .perform(get("/conversations").header("X-User-Id", FORGED))
                .andExpect(status().isOk());

        ArgumentCaptor<UUID> userId = ArgumentCaptor.forClass(UUID.class);
        verify(conversationService).getUserConversations(userId.capture());
        assertEquals(authenticatedUserId, userId.getValue());
    }

    @Test
    void withoutAuthenticationConversationListStaysRejectedInsteadOfTrustingTheHeader() throws Exception {
        withoutAuth(new ConversationController(conversationService))
                .perform(get("/conversations").header("X-User-Id", FORGED))
                .andExpect(status().isBadRequest());
    }

    @Test
    void customRoleIdentityComesOnlyFromTheAuthenticatedContext() throws Exception {
        when(roleService.getCustomRoles(any(UUID.class))).thenReturn(List.of());

        withAuth(new RoleController(roleService, org.mockito.Mockito.mock(
                com.kinlin.ai.service.RoleSwitchOptimizer.class)))
                .perform(get("/roles/custom").header("X-User-Id", FORGED))
                .andExpect(status().isOk());

        ArgumentCaptor<UUID> userId = ArgumentCaptor.forClass(UUID.class);
        verify(roleService).getCustomRoles(userId.capture());
        assertEquals(authenticatedUserId, userId.getValue());
    }

    @Test
    void currentUserEndpointIdentityComesOnlyFromTheAuthenticatedContext() throws Exception {
        when(userService.getUserById(any(UUID.class))).thenReturn(Optional.of(new com.kinlin.ai.entity.User()));

        withAuth(new UserController(userService, org.mockito.Mockito.mock(com.kinlin.ai.service.FileService.class)))
                .perform(get("/users/me").header("X-User-Id", FORGED))
                .andExpect(status().isOk());

        ArgumentCaptor<UUID> userId = ArgumentCaptor.forClass(UUID.class);
        verify(userService).getUserById(userId.capture());
        assertEquals(authenticatedUserId, userId.getValue());
    }

    @Test
    void chatQualityOwnershipComesOnlyFromTheAuthenticatedContext() throws Exception {
        when(chatService.getHistory(anyString(), any(UUID.class))).thenReturn(List.of());
        when(qualityService.assessQuality(any())).thenReturn(new ChatQualityService.QualityScore(0.9, "ok"));

        withAuth(new ChatQualityController(qualityService, chatService))
                .perform(get("/chat/quality/{contextId}", "c1").header("X-User-Id", FORGED))
                .andExpect(status().isOk());

        ArgumentCaptor<UUID> userId = ArgumentCaptor.forClass(UUID.class);
        verify(chatService).getHistory(anyString(), userId.capture());
        assertEquals(authenticatedUserId, userId.getValue());
    }

    private MockMvc withAuth(Object controller) {
        return MockMvcBuilders.standaloneSetup(controller)
                .addFilters(new SensitiveIdentityHeaderFilter(),
                        new AuthenticatedContextFilter(authenticatedUserId))
                .build();
    }

    private MockMvc withoutAuth(Object controller) {
        return MockMvcBuilders.standaloneSetup(controller)
                .addFilters(new SensitiveIdentityHeaderFilter())
                .build();
    }

    /** Standalone 测试环境没有 JWT 过滤器；等价地直接重建认证上下文。 */
    private static final class AuthenticatedContextFilter extends OncePerRequestFilter {

        private final UUID userId;

        private AuthenticatedContextFilter(UUID userId) {
            this.userId = userId;
        }

        @Override
        protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                        FilterChain filterChain) throws ServletException, IOException {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken(
                            new AuthenticatedUserContext(userId, "subject", "USER", null, null),
                            null, List.of()));
            try {
                filterChain.doFilter(request, response);
            } finally {
                SecurityContextHolder.clearContext();
            }
        }
    }
}
