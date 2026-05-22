package com.kinlin.ai.service;

import com.kinlin.ai.entity.User;
import com.kinlin.ai.repository.UserRepository;
import com.kinlin.ai.util.PasswordUtil;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * UserService单元测试
 */
@ExtendWith(MockitoExtension.class)
class UserServiceTest {

    @Mock
    private UserRepository userRepository;

    @InjectMocks
    private UserService userService;

    private User testUser;
    private UUID userId;
    private String username;
    private String password;

    @BeforeEach
    void setUp() {
        userId = UUID.randomUUID();
        username = "testuser";
        password = "testpassword123";

        testUser = new User();
        testUser.setId(userId);
        testUser.setUsername(username);
        testUser.setPasswordHash(PasswordUtil.encode(password));
    }

    @Test
    void testGetUserByUsername_Success() {
        // Given
        when(userRepository.findByUsername(username)).thenReturn(Optional.of(testUser));

        // When
        Optional<User> result = userService.getUserByUsername(username);

        // Then
        assertTrue(result.isPresent());
        assertEquals(username, result.get().getUsername());
        verify(userRepository).findByUsername(username);
    }

    @Test
    void testGetUserByUsername_NotFound() {
        // Given
        when(userRepository.findByUsername(username)).thenReturn(Optional.empty());

        // When
        Optional<User> result = userService.getUserByUsername(username);

        // Then
        assertFalse(result.isPresent());
    }

    @Test
    void testGetUserById_Success() {
        // Given
        when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));

        // When
        Optional<User> result = userService.getUserById(userId);

        // Then
        assertTrue(result.isPresent());
        assertEquals(userId, result.get().getId());
    }

    @Test
    void testCreateUser_Success() {
        // Given
        String email = "test@example.com";
        when(userRepository.findByUsername(username)).thenReturn(Optional.empty());
        when(userRepository.findByEmail(email)).thenReturn(Optional.empty());
        when(userRepository.save(any(User.class))).thenReturn(testUser);

        // When
        User result = userService.createUser(username, password, email);

        // Then
        assertNotNull(result);
        assertEquals(username, result.getUsername());
        assertNotNull(result.getPasswordHash());
        assertTrue(PasswordUtil.matches(password, result.getPasswordHash()));
        verify(userRepository).save(any(User.class));
    }

    @Test
    void testCreateUser_UsernameExists() {
        // Given
        when(userRepository.findByUsername(username)).thenReturn(Optional.of(testUser));

        // When & Then
        assertThrows(IllegalArgumentException.class, () -> {
            userService.createUser(username, password, null);
        });
    }

    @Test
    void testCreateUser_EmailExists() {
        // Given
        String email = "test@example.com";
        when(userRepository.findByUsername(username)).thenReturn(Optional.empty());
        when(userRepository.findByEmail(email)).thenReturn(Optional.of(testUser));

        // When & Then
        assertThrows(IllegalArgumentException.class, () -> {
            userService.createUser(username, password, email);
        });
    }

    @Test
    void testValidateUser_Success() {
        // Given
        when(userRepository.findByUsername(username)).thenReturn(Optional.of(testUser));

        // When
        Optional<User> result = userService.validateUser(username, password);

        // Then
        assertTrue(result.isPresent());
        assertEquals(username, result.get().getUsername());
    }

    @Test
    void testValidateUser_WrongPassword() {
        // Given
        when(userRepository.findByUsername(username)).thenReturn(Optional.of(testUser));

        // When
        Optional<User> result = userService.validateUser(username, "wrongpassword");

        // Then
        assertFalse(result.isPresent());
    }

    @Test
    void testValidateUser_UserNotFound() {
        // Given
        when(userRepository.findByUsername(username)).thenReturn(Optional.empty());

        // When
        Optional<User> result = userService.validateUser(username, password);

        // Then
        assertFalse(result.isPresent());
    }

    @Test
    void testValidateUser_NoPasswordHash() {
        // Given
        testUser.setPasswordHash(null);
        when(userRepository.findByUsername(username)).thenReturn(Optional.of(testUser));

        // When
        Optional<User> result = userService.validateUser(username, password);

        // Then
        assertFalse(result.isPresent());
    }

    @Test
    void testUpdatePassword_Success() {
        // Given
        String newPassword = "newpassword123";
        when(userRepository.findById(userId)).thenReturn(Optional.of(testUser));
        when(userRepository.save(any(User.class))).thenReturn(testUser);

        // When
        userService.updatePassword(userId, newPassword);

        // Then
        verify(userRepository).save(any(User.class));
        assertTrue(PasswordUtil.matches(newPassword, testUser.getPasswordHash()));
    }

    @Test
    void testUpdatePassword_UserNotFound() {
        // Given
        when(userRepository.findById(userId)).thenReturn(Optional.empty());

        // When & Then
        assertThrows(IllegalArgumentException.class, () -> {
            userService.updatePassword(userId, "newpassword");
        });
    }

    @Test
    void testUpdateUser_Success() {
        // Given
        testUser.setEmail("newemail@example.com");
        when(userRepository.save(testUser)).thenReturn(testUser);

        // When
        User result = userService.updateUser(testUser);

        // Then
        assertNotNull(result);
        assertEquals("newemail@example.com", result.getEmail());
        verify(userRepository).save(testUser);
    }

    @Test
    void testDeleteUser_Success() {
        // When
        userService.deleteUser(userId);

        // Then
        verify(userRepository).deleteById(userId);
    }
}

