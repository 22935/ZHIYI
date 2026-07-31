package com.kinlin.ai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 对话请求DTO
 */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ChatRequest {

    private String text;

    private UUID roleId;

    private String contextId;

    private String fileUrl; // 文件URL（图片、文档等）
    
    private Boolean useRag; // 是否使用RAG增强
    
    private List<Map<String, String>> context; // 对话上下文（可选，如果提供则使用，否则从数据库构建）

    private String model;

    private String baseUrl;

    private String apiKey;

    private String thinkingMode;

    // Compatibility with clients that still send off/low/medium/high.
    private String reasoningEffort;

    private String toolMode;
}
