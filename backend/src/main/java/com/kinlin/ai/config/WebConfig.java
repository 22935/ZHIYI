package com.kinlin.ai.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.List;

/**
 * Web配置类
 * 配置跨域等Web相关设置
 */
@Configuration
@EnableConfigurationProperties(WebConfig.CorsProperties.class)
public class WebConfig implements WebMvcConfigurer {

    private final CorsProperties corsProperties;

    public WebConfig(CorsProperties corsProperties) {
        this.corsProperties = corsProperties;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        CorsProperties cors = corsProperties != null ? corsProperties : new CorsProperties();
        registry.addMapping("/**")
                .allowedOrigins(cors.getAllowedOrigins() != null && !cors.getAllowedOrigins().isEmpty() 
                    ? cors.getAllowedOrigins().toArray(new String[0]) 
                    : new String[]{"*"})
                .allowedMethods(cors.getAllowedMethods() != null && !cors.getAllowedMethods().isEmpty()
                    ? cors.getAllowedMethods().toArray(new String[0])
                    : new String[]{"GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"})
                .allowedHeaders(cors.getAllowedHeaders() != null ? cors.getAllowedHeaders() : "*")
                .exposedHeaders("X-Trace-Id")
                .allowCredentials(cors.isAllowCredentials())
                .maxAge(3600);
    }

    @Data
    @ConfigurationProperties(prefix = "cors")
    public static class CorsProperties {
        private List<String> allowedOrigins;
        private List<String> allowedMethods;
        private String allowedHeaders = "*";
        private boolean allowCredentials = true;
    }
}

