package com.kinlin.ai.controller;

import com.kinlin.ai.dto.LoginRequest;
import com.kinlin.ai.dto.LoginResponse;
import com.kinlin.ai.entity.User;
import com.kinlin.ai.service.UserService;
import com.kinlin.ai.util.JwtUtil;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * 认证控制器
 * 处理用户登录、注册等认证相关功能
 */
@Slf4j
@RestController
@RequestMapping("/auth")
@RequiredArgsConstructor
public class AuthController {

    private final UserService userService;
    private final JwtUtil jwtUtil;

    /**
     * 用户登录
     */
    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        LoginResponse response = new LoginResponse();

        // 验证用户和密码
        Optional<User> userOpt = userService.validateUser(
                request.getUsername(),
                request.getPassword() != null ? request.getPassword() : ""
        );

        if (userOpt.isEmpty()) {
            response.setMessage("用户名或密码错误");
            return ResponseEntity.status(401).body(response);
        }

        User user = userOpt.get();
        String token = jwtUtil.generateToken(user.getId(), user.getUsername());

        response.setToken(token);
        response.setUserId(user.getId());
        response.setUsername(user.getUsername());
        response.setMessage("登录成功");

        return ResponseEntity.ok(response);
    }

    /**
     * 用户注册
     */
    @PostMapping("/register")
    public ResponseEntity<LoginResponse> register(@Valid @RequestBody LoginRequest request) {
        LoginResponse response = new LoginResponse();

        // 验证必填字段
        if (request.getUsername() == null || request.getUsername().trim().isEmpty()) {
            response.setMessage("用户名不能为空");
            return ResponseEntity.badRequest().body(response);
        }

        if (request.getPassword() == null || request.getPassword().trim().isEmpty()) {
            response.setMessage("密码不能为空");
            return ResponseEntity.badRequest().body(response);
        }

        // 检查用户名是否已存在
        if (userService.getUserByUsername(request.getUsername()).isPresent()) {
            response.setMessage("用户名已存在");
            return ResponseEntity.badRequest().body(response);
        }

        try {
            // 创建新用户（密码会自动加密）
            User user = userService.createUser(
                    request.getUsername(),
                    request.getPassword(),
                    request.getEmail()
            );

            String token = jwtUtil.generateToken(user.getId(), user.getUsername());

            response.setToken(token);
            response.setUserId(user.getId());
            response.setUsername(user.getUsername());
            response.setMessage("注册成功");

            return ResponseEntity.ok(response);
        } catch (IllegalArgumentException e) {
            response.setMessage(e.getMessage());
            return ResponseEntity.badRequest().body(response);
        }
    }

    /**
     * 验证Token
     */
    @GetMapping("/verify")
    public ResponseEntity<Map<String, Object>> verifyToken(
            @RequestHeader(value = "Authorization", required = false) String authHeader
    ) {
        Map<String, Object> result = new HashMap<>();
        
        try {
            if (authHeader == null || !authHeader.regionMatches(true, 0, "Bearer ", 0, 7)) {
                result.put("valid", false);
                result.put("message", "Missing or invalid Authorization header");
                return ResponseEntity.ok(result);
            }

            String token = authHeader.substring(7).trim();
            if (token.isEmpty()) {
                result.put("valid", false);
                result.put("message", "Token is empty");
                return ResponseEntity.ok(result);
            }

            String username = jwtUtil.getUsernameFromToken(token);
            UUID userId = jwtUtil.getUserIdFromToken(token);
            
            if (jwtUtil.validateToken(token, username)) {
                result.put("valid", true);
                result.put("userId", userId);
                result.put("username", username);
            } else {
                result.put("valid", false);
                result.put("message", "Token无效或已过期");
            }
        } catch (Exception e) {
            result.put("valid", false);
            result.put("message", "Token验证失败: " + e.getMessage());
        }
        
        return ResponseEntity.ok(result);
    }
}

