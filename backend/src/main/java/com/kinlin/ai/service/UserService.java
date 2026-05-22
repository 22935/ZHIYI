package com.kinlin.ai.service;

import com.kinlin.ai.entity.User;
import com.kinlin.ai.repository.UserRepository;
import com.kinlin.ai.util.PasswordUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Optional;
import java.util.UUID;

/**
 * 用户服务类
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;

    /**
     * 根据用户名获取用户
     */
    public Optional<User> getUserByUsername(String username) {
        return userRepository.findByUsername(username);
    }

    /**
     * 根据ID获取用户
     */
    public Optional<User> getUserById(UUID userId) {
        return userRepository.findById(userId);
    }

    /**
     * 根据邮箱获取用户
     */
    public Optional<User> getUserByEmail(String email) {
        return userRepository.findByEmail(email);
    }

    /**
     * 创建用户（带密码加密）
     *
     * @param username 用户名
     * @param password 原始密码（将自动加密）
     * @param email    邮箱（可选）
     * @return 创建的用户
     */
    @Transactional
    public User createUser(String username, String password, String email) {
        // 检查用户名是否已存在
        if (userRepository.findByUsername(username).isPresent()) {
            throw new IllegalArgumentException("用户名已存在");
        }

        // 检查邮箱是否已存在（如果提供）
        if (email != null && !email.isEmpty()) {
            if (userRepository.findByEmail(email).isPresent()) {
                throw new IllegalArgumentException("邮箱已被使用");
            }
        }

        User user = new User();
        user.setUsername(username);
        user.setEmail(email);

        // 加密密码
        if (password != null && !password.isEmpty()) {
            user.setPasswordHash(PasswordUtil.encode(password));
        }

        return userRepository.save(user);
    }

    /**
     * 创建用户（简化版本，兼容旧代码）
     */
    @Transactional
    public User createUser(String username, String passwordHash) {
        return createUser(username, passwordHash, null);
    }

    /**
     * 验证用户密码
     *
     * @param username 用户名
     * @param password 原始密码
     * @return 用户对象（如果验证成功）
     */
    public Optional<User> validateUser(String username, String password) {
        Optional<User> userOpt = getUserByUsername(username);
        if (userOpt.isEmpty()) {
            return Optional.empty();
        }

        User user = userOpt.get();
        String encodedPassword = user.getPasswordHash();

        if (encodedPassword == null || encodedPassword.isEmpty()) {
            log.warn("User {} has no password hash and cannot log in.", username);
            return Optional.empty();
        }

        // 验证密码
        if (PasswordUtil.matches(password, encodedPassword)) {
            return userOpt;
        }

        return Optional.empty();
    }

    /**
     * 更新用户密码
     *
     * @param userId      用户ID
     * @param newPassword 新密码（原始密码，将自动加密）
     */
    @Transactional
    public void updatePassword(UUID userId, String newPassword) {
        User user = getUserById(userId)
                .orElseThrow(() -> new IllegalArgumentException("用户不存在"));

        user.setPasswordHash(PasswordUtil.encode(newPassword));
        userRepository.save(user);
        log.info("用户 {} 密码已更新", userId);
    }

    /**
     * 更新用户
     */
    @Transactional
    public User updateUser(User user) {
        return userRepository.save(user);
    }

    /**
     * 删除用户
     */
    @Transactional
    public void deleteUser(UUID userId) {
        userRepository.deleteById(userId);
    }
}
