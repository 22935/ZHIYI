package com.kinlin.ai.config;

import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;

/**
 * JWT配置类
 * 用于JWT Token生成和验证
 */
@Configuration
public class JwtConfig {

    @Value("${app.jwt.secret:federal-hub-secret-key-change-in-production}")
    private String secret;

    @Value("${app.jwt.expiration:86400000}") // 24小时
    private Long expiration;

    @Bean
    public SecretKey secretKey() {
        return Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    public Long getExpiration() {
        return expiration;
    }
}

