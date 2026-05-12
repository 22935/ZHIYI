package com.kinlin.ai;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

/**
 * 联邦智枢 后端应用主类
 * 
 * @author 联邦智枢 Team
 * @version 1.0.0
 */
@SpringBootApplication
@EnableJpaAuditing
public class KinlinAiApplication {

    public static void main(String[] args) {
        SpringApplication.run(KinlinAiApplication.class, args);
    }
}

