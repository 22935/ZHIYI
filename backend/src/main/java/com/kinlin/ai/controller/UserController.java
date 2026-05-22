package com.kinlin.ai.controller;

import com.kinlin.ai.entity.User;
import com.kinlin.ai.security.AuthenticatedUser;
import com.kinlin.ai.service.UserService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

/**
 * 用户控制器
 */
@RestController
@RequestMapping("/users")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    /**
     * 获取当前用户信息
     */
    @GetMapping("/me")
    public ResponseEntity<User> getCurrentUser(
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        UUID currentUserId = resolveUserId(userId);
        if (currentUserId == null) {
            return ResponseEntity.badRequest().build();
        }
        return userService.getUserById(currentUserId)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * 获取用户信息
     */
    @GetMapping("/{userId}")
    public ResponseEntity<User> getUser(@PathVariable UUID userId) {
        return userService.getUserById(userId)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * 更新用户信息
     */
    @PutMapping("/{userId}")
    public ResponseEntity<User> updateUser(
            @PathVariable UUID userId,
            @RequestHeader(value = "X-User-Id", required = false) UUID currentUserId,
            @RequestBody User userUpdate
    ) {
        currentUserId = resolveUserId(currentUserId);
        // 验证用户只能更新自己的信息
        if (currentUserId == null || !currentUserId.equals(userId)) {
            return ResponseEntity.badRequest().build();
        }

        return userService.getUserById(userId)
                .map(user -> {
                    // 只更新允许的字段
                    if (userUpdate.getEmail() != null) {
                        user.setEmail(userUpdate.getEmail());
                    }
                    if (userUpdate.getUsername() != null) {
                        user.setUsername(userUpdate.getUsername());
                    }
                    User updated = userService.updateUser(user);
                    return ResponseEntity.ok(updated);
                })
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * 修改密码
     */
    @PostMapping("/{userId}/password")
    public ResponseEntity<Void> changePassword(
            @PathVariable UUID userId,
            @RequestHeader(value = "X-User-Id", required = false) UUID currentUserId,
            @RequestBody PasswordChangeRequest request
    ) {
        currentUserId = resolveUserId(currentUserId);
        // 验证用户只能修改自己的密码
        if (currentUserId == null || !currentUserId.equals(userId)) {
            return ResponseEntity.badRequest().build();
        }

        // 验证当前密码
        User user = userService.getUserById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        if (!userService.validateUser(user.getUsername(), request.getCurrentPassword()).isPresent()) {
            return ResponseEntity.badRequest().build();
        }

        // 更新密码
        userService.updatePassword(userId, request.getNewPassword());
        return ResponseEntity.ok().build();
    }

    private UUID resolveUserId(UUID userIdHeader) {
        return AuthenticatedUser.currentUserId().orElse(userIdHeader);
    }

    /**
     * 密码修改请求DTO
     */
    public static class PasswordChangeRequest {
        private String currentPassword;
        private String newPassword;

        public String getCurrentPassword() {
            return currentPassword;
        }

        public void setCurrentPassword(String currentPassword) {
            this.currentPassword = currentPassword;
        }

        public String getNewPassword() {
            return newPassword;
        }

        public void setNewPassword(String newPassword) {
            this.newPassword = newPassword;
        }
    }
}

