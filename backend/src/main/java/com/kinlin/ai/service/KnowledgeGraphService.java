package com.kinlin.ai.service;

import com.kinlin.ai.dto.KnowledgeGraphRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 知识图谱服务
 * 负责与Python AI服务的知识图谱功能通信
 */
@Slf4j
@Service
public class KnowledgeGraphService {

    private final WebClient webClient;

    @Value("${ai.service.url}")
    private String aiServiceUrl;

    @Value("${ai.service.timeout}")
    private int timeout;

    public KnowledgeGraphService(WebClient.Builder webClientBuilder, 
                                 @Value("${ai.service.url}") String aiServiceUrl, 
                                 @Value("${ai.service.timeout}") int timeout) {
        this.aiServiceUrl = aiServiceUrl;
        this.timeout = timeout;
        this.webClient = webClientBuilder
                .baseUrl(aiServiceUrl)
                .build();
    }

    /**
     * 从文档构建知识图谱
     */
    public Map<String, Object> buildKnowledgeGraph(List<KnowledgeGraphRequest.DocumentInfo> documents) {
        return buildKnowledgeGraph(documents, null);
    }

    /**
     * 从文档构建知识图谱
     */
    public Map<String, Object> buildKnowledgeGraph(List<KnowledgeGraphRequest.DocumentInfo> documents, String roleId) {
        try {
            List<Map<String, Object>> docs = documents.stream()
                    .map(doc -> {
                        Map<String, Object> docMap = new HashMap<>();
                        docMap.put("doc_id", doc.getDocId());
                        docMap.put("text", doc.getText());
                        if (doc.getMetadata() != null) {
                            docMap.put("metadata", doc.getMetadata());
                        }
                        return docMap;
                    })
                    .collect(Collectors.toList());

            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("documents", docs);
            if (roleId != null && !roleId.isBlank()) {
                requestBody.put("role_id", roleId);
            }

            Map<String, Object> responseMap = webClient.post()
                    .uri("/api/knowledge-graph/build")
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(Map.class)
                    .timeout(Duration.ofMillis(timeout))
                    .block();

            if (responseMap != null && Boolean.TRUE.equals(responseMap.get("success"))) {
                return (Map<String, Object>) responseMap.get("data");
            }
            return new HashMap<>();
        } catch (Exception e) {
            log.error("构建知识图谱失败", e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("error", "构建知识图谱失败: " + e.getMessage());
            return errorResponse;
        }
    }

    /**
     * 混合检索：知识图谱 + 向量数据库
     */
    public Map<String, Object> hybridSearch(String question, List<Map<String, Object>> vectorDbResults, Integer topK) {
        try {
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("question", question);
            requestBody.put("vector_db_results", vectorDbResults);
            requestBody.put("top_k", topK != null ? topK : 5);

            Map<String, Object> responseMap = webClient.post()
                    .uri("/api/knowledge-graph/search")
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(Map.class)
                    .timeout(Duration.ofMillis(timeout))
                    .block();

            if (responseMap != null && Boolean.TRUE.equals(responseMap.get("success"))) {
                return (Map<String, Object>) responseMap.get("data");
            }
            return new HashMap<>();
        } catch (Exception e) {
            log.error("混合检索失败", e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("error", "混合检索失败: " + e.getMessage());
            return errorResponse;
        }
    }

    /**
     * 基于知识图谱进行推理
     */
    public Map<String, Object> reasonWithKnowledgeGraph(String question) {
        try {
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("question", question);

            Map<String, Object> responseMap = webClient.post()
                    .uri("/api/knowledge-graph/reason")
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(Map.class)
                    .timeout(Duration.ofMillis(timeout))
                    .block();

            if (responseMap != null && Boolean.TRUE.equals(responseMap.get("success"))) {
                return (Map<String, Object>) responseMap.get("data");
            }
            return new HashMap<>();
        } catch (Exception e) {
            log.error("知识推理失败", e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("error", "知识推理失败: " + e.getMessage());
            return errorResponse;
        }
    }

    /**
     * 获取知识图谱统计信息
     */
    public Map<String, Object> getGraphStats() {
        try {
            Map<String, Object> responseMap = webClient.get()
                    .uri("/api/knowledge-graph/stats")
                    .retrieve()
                    .bodyToMono(Map.class)
                    .timeout(Duration.ofMillis(timeout))
                    .block();

            if (responseMap != null && Boolean.TRUE.equals(responseMap.get("success"))) {
                return (Map<String, Object>) responseMap.get("data");
            }
            return new HashMap<>();
        } catch (Exception e) {
            log.error("获取知识图谱统计信息失败", e);
            return new HashMap<>();
        }
    }

    /**
     * 查询实体相关信息
     */
    public Map<String, Object> getEntityInfo(String entityId, String relation, Integer limit) {
        try {
            StringBuilder uriBuilder = new StringBuilder("/api/knowledge-graph/entity/").append(entityId);
            if (relation != null) {
                uriBuilder.append("?relation=").append(relation);
            }
            if (limit != null) {
                uriBuilder.append(relation != null ? "&" : "?").append("limit=").append(limit);
            }

            Map<String, Object> responseMap = webClient.get()
                    .uri(uriBuilder.toString())
                    .retrieve()
                    .bodyToMono(Map.class)
                    .timeout(Duration.ofMillis(timeout))
                    .block();

            if (responseMap != null && Boolean.TRUE.equals(responseMap.get("success"))) {
                return (Map<String, Object>) responseMap.get("data");
            }
            return new HashMap<>();
        } catch (Exception e) {
            log.error("查询实体信息失败", e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("error", "查询实体信息失败: " + e.getMessage());
            return errorResponse;
        }
    }

    /**
     * 获取完整的知识图谱数据（用于可视化）
     */
    public Map<String, Object> getGraphData(String roleId) {
        try {
            StringBuilder uriBuilder = new StringBuilder("/api/knowledge-graph/graph-data");
            if (roleId != null && !roleId.isEmpty()) {
                uriBuilder.append("?role_id=").append(roleId);
            }

            @SuppressWarnings("unchecked")
            Map<String, Object> responseMap = webClient.get()
                    .uri(uriBuilder.toString())
                    .retrieve()
                    .bodyToMono(Map.class)
                    .timeout(Duration.ofMillis(timeout))
                    .block();

            if (responseMap != null && Boolean.TRUE.equals(responseMap.get("success"))) {
                @SuppressWarnings("unchecked")
                Map<String, Object> data = (Map<String, Object>) responseMap.get("data");
                return data != null ? data : new HashMap<>();
            }
            return new HashMap<>();
        } catch (Exception e) {
            log.error("获取知识图谱数据失败", e);
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("error", "获取知识图谱数据失败: " + e.getMessage());
            return errorResponse;
        }
    }
}

