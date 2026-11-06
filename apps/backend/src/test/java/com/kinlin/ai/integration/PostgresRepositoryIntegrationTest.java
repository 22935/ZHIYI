package com.kinlin.ai.integration;

import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.entity.Role;
import com.kinlin.ai.entity.User;
import com.kinlin.ai.repository.ConversationRepository;
import com.kinlin.ai.repository.MessageRepository;
import com.kinlin.ai.repository.RoleRepository;
import com.kinlin.ai.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * J1.4A §十/§十一/§十八：真实 PostgreSQL 上的代表性 Repository 集成。
 *
 * <p>覆盖核心实体 User / Role / Conversation / Message 的代表性路径
 * （insert、select by id、自定义 @Query、真实存在的约束、事务回滚、
 * UUID/jsonb/CHECK 等 PostgreSQL 特有语义）。只断言真实 schema
 * （注意：项目 schema 无外键约束，故约束测试覆盖 UNIQUE + CHECK），
 * 不为证明 PostgreSQL 人造特性。</p>
 */
@SpringBootTest
class PostgresRepositoryIntegrationTest extends PostgresIntegrationTestBase {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private RoleRepository roleRepository;

    @Autowired
    private ConversationRepository conversationRepository;

    @Autowired
    private MessageRepository messageRepository;

    @Autowired
    private TransactionTemplate transactionTemplate;

    @Test
    void insertAndSelectByIdRoundTripsUuidPrimaryKey() {
        User user = new User();
        user.setUsername("pg_it_user_" + UUID.randomUUID());
        user.setEmail("pg_it_" + UUID.randomUUID() + "@example.com");
        User saved = userRepository.saveAndFlush(user);

        assertThat(saved.getId()).isNotNull();
        User reloaded = userRepository.findById(saved.getId()).orElseThrow();
        assertThat(reloaded.getUsername()).isEqualTo(saved.getUsername());
        assertThat(reloaded.getId()).isEqualTo(saved.getId());
        assertThat(reloaded.getCreatedAt()).isNotNull();
    }

    @Test
    void customJpqlQueryReturnsConversationsOrderedByUpdatedAtDesc() {
        UUID userId = UUID.randomUUID();
        Conversation first = conversation(userId, "pg_it_ctx_" + UUID.randomUUID());
        Conversation second = conversation(userId, "pg_it_ctx_" + UUID.randomUUID());
        conversationRepository.saveAllAndFlush(List.of(first, second));

        // updatedAt 由 auditing 填充，显式拉开顺序保证确定性
        second.setTitle("bump");
        sleepQuietly(5);
        conversationRepository.saveAndFlush(second);

        List<Conversation> recent = conversationRepository.findRecentConversationsByUserId(userId);
        assertThat(recent).hasSize(2);
        assertThat(recent.get(0).getId()).isEqualTo(second.getId());
    }

    @Test
    void uniqueConstraintRejectsDuplicateUsername() {
        String username = "pg_it_dup_" + UUID.randomUUID();
        User first = new User();
        first.setUsername(username);
        userRepository.saveAndFlush(first);

        User duplicate = new User();
        duplicate.setUsername(username);
        assertThatThrownBy(() -> userRepository.saveAndFlush(duplicate))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void checkConstraintRejectsInvalidWorkspaceMode() {
        Conversation conversation = conversation(UUID.randomUUID(),
                "pg_it_ctx_" + UUID.randomUUID());
        // schema CHECK chk_conversations_workspace_mode 只允许 'agent' / 'chat'
        conversation.setWorkspaceMode("bogus");
        assertThatThrownBy(() -> conversationRepository.saveAndFlush(conversation))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void jsonbColumnsRoundTripStructuredValues() {
        Role role = new Role();
        role.setName("pg_it_role_" + UUID.randomUUID());
        role.setRoleType(Role.RoleType.CUSTOM);
        Map<String, Object> dialogueStyle = Map.of("formality", 0.8, "warmth", 0.3);
        Map<String, Object> personality = Map.of("严谨", true, "耐心", false);
        role.setDialogueStyle(new java.util.HashMap<>(dialogueStyle));
        role.setPersonality(new java.util.HashMap<>(personality));
        Role savedRole = roleRepository.saveAndFlush(role);
        Role reloadedRole = roleRepository.findById(savedRole.getId()).orElseThrow();
        assertThat(reloadedRole.getDialogueStyle()).isEqualTo(dialogueStyle);
        assertThat(reloadedRole.getPersonality()).isEqualTo(personality);

        Message message = new Message();
        message.setConversationId(UUID.randomUUID());
        message.setRole(Message.MessageRole.USER);
        message.setContent("jsonb round trip");
        Map<String, Object> metadata = Map.of(
                "origin", "pg-it",
                "nested", Map.of("depth", 2));
        message.setMetadata(new java.util.HashMap<>(metadata));
        Message savedMessage = messageRepository.saveAndFlush(message);
        Message reloadedMessage = messageRepository.findById(savedMessage.getId()).orElseThrow();
        assertThat(reloadedMessage.getMetadata()).isEqualTo(metadata);
    }

    /**
     * §十八：事务回滚表征——事务内写入后主动抛异常，数据必须未落库。
     * 与 ChatService 的 TransactionTemplate 短事务模式同构。
     */
    @Test
    void transactionRollbackDiscardsWritesInsideTemplate() {
        UUID conversationId = UUID.randomUUID();

        assertThatThrownBy(() -> transactionTemplate.execute((TransactionStatus status) -> {
            Message message = new Message();
            message.setConversationId(conversationId);
            message.setRole(Message.MessageRole.USER);
            message.setContent("must not survive rollback");
            messageRepository.save(message);
            messageRepository.flush();
            throw new IllegalStateException("rollback characterization");
        })).isInstanceOf(IllegalStateException.class);

        assertThat(messageRepository.findByConversationIdOrderByCreatedAtAsc(conversationId)).isEmpty();
    }

    private static Conversation conversation(UUID userId, String contextId) {
        Conversation conversation = new Conversation();
        conversation.setUserId(userId);
        conversation.setContextId(contextId);
        conversation.setWorkspaceMode("chat");
        return conversation;
    }

    private static void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
