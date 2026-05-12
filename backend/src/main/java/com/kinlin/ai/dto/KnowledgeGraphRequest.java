package com.kinlin.ai.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import java.util.List;
import java.util.Map;

/**
 * 知识图谱请求DTO
 */
@Data
public class KnowledgeGraphRequest {
    private List<DocumentInfo> documents;
    private String question;
    private List<Map<String, Object>> vectorDbResults;
    private Integer topK = 5;
    @JsonProperty("role_id")
    private String roleId;
    
    @Data
    public static class DocumentInfo {
        private String docId;
        private String text;
        private Map<String, Object> metadata;
    }
}

