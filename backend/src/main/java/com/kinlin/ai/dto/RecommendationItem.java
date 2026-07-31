package com.kinlin.ai.dto;

import lombok.Data;

@Data
/** 推荐项 DTO — 包含推荐文本、理由、目标动作、置信度和适用范围 */
public class RecommendationItem {

    private String text;

    private String reason;

    private String targetAction;

    private double confidence;

    private String scope;
}
