package com.kinlin.ai.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 对话响应DTO
 */
@Data
public class ChatResponse {

    private String text;

    private String contextId;

    private Double confidence;

    @JsonAlias("tokens_used")
    private Integer tokensUsed;

    private Object animation; // 数字人动画数据
    
    @JsonAlias("recognized_text")
    private String recognizedText; // 语音识别结果（仅用于语音对话）
    
    // 可解释性字段
    private List<Map<String, Object>> sources; // RAG来源
    @JsonAlias("reasoning_path")
    private List<Map<String, String>> reasoningPath; // 推理路径
    @JsonAlias("model_info")
    private String modelInfo; // 使用的模型信息
    private Map<String, Object> metadata; // 其他元数据
}

