package com.kinlin.ai.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;

import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
/** 推荐上下文请求 DTO — 包含角色名称、范围、场景、当前输入/输出和对话历史 */
public class RecommendationContextRequest {

    private String roleName;

    private String scope;

    private String scene;

    private String currentInput;

    private String currentOutput;

    private List<String> conversationHistory;
}
