package com.kinlin.ai.infrastructure.http;

import com.kinlin.ai.client.AiChatClient;
import com.kinlin.ai.client.PlatformAiClientException;
import com.kinlin.ai.client.RagClient;
import com.kinlin.ai.dto.ChatResponse;
import com.kinlin.ai.dto.KnowledgeGraphRequest;
import com.kinlin.ai.dto.RoleFusionRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpMethod;
import org.springframework.web.reactive.function.client.WebClientRequestException;

import java.net.ConnectException;
import java.net.URI;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 平台 AI client 实现表征测试：真实 WebClient 序列化路径（method/URI/body 经默认
 * codecs）+ transport 错误分类（REJECTED/UPSTREAM_ERROR/TIMEOUT/UNAVAILABLE）。
 */
class PlatformAiClientCharacterizationTest {

    private static final String BASE = "http://python.test";

    private FakePythonTransport upstream;
    private PlatformAiTransport transport;

    @BeforeEach
    void setUp() {
        upstream = new FakePythonTransport();
        PythonServiceProperties properties = new PythonServiceProperties();
        properties.setTimeout(2_000);
        transport = new PlatformAiTransport(upstream.client(BASE), properties);
    }

    @Nested
    class RagClientImpl {

        private WebClientRagClient client;

        @BeforeEach
        void setUpClient() {
            client = new WebClientRagClient(transport);
        }

        @Test
        void queryPostsQueryCommandWithDefaultTopK() {
            upstream.willReturn(200,
                    "{\"answer\":\"答案\",\"sources\":[{\"doc_id\":\"d1\"}],\"confidence\":0.9}");

            RagClient.RagQueryResult result = client.query(
                    new RagClient.RagQueryCommand("合同要点", null, "ctx-1", "role-1", true));

            assertEquals(HttpMethod.POST, upstream.lastMethod());
            assertEquals("/rag/query", upstream.lastUri().getPath());
            String body = upstream.lastBodyJson();
            assertTrue(body.contains("\"query\":\"合同要点\""));
            assertTrue(body.contains("\"top_k\":5"));
            assertTrue(body.contains("\"context_id\":\"ctx-1\""));
            assertTrue(body.contains("\"role_id\":\"role-1\""));
            assertTrue(body.contains("\"use_knowledge_graph\":true"));
            assertEquals("答案", result.answer());
            assertEquals(0.9, result.confidence());
        }

        @Test
        void uploadSendsMultipartWithRolePartAndReturnsDocumentId() {
            upstream.willReturn(200, "{\"document_id\":\"doc-9\"}");

            String documentId = client.uploadDocument(new RagClient.DocumentUpload(
                    new ByteArrayResource("content".getBytes()), "notes.txt", "text/plain", "role-1"));

            assertEquals(HttpMethod.POST, upstream.lastMethod());
            assertEquals("/rag/documents", upstream.lastUri().getPath());
            String body = upstream.lastBodyJson();
            assertTrue(body.contains("filename=\"notes.txt\""), body);
            assertTrue(body.contains("name=\"role_id\""), body);
            assertEquals("doc-9", documentId);
        }

        @Test
        void listDocumentsAppendsRoleIdQuery() {
            upstream.willReturn(200, "{\"documents\":[],\"count\":0}");

            Map<String, Object> result = client.listDocuments("role-1");

            assertEquals("/rag/documents", upstream.lastUri().getPath());
            assertEquals("role_id=role-1", upstream.lastUri().getQuery());
            assertTrue(result.containsKey("documents"));
        }

        @Test
        void deleteUsesConcatenatedPathLikeTheFormerService() {
            upstream.willReturn(200, "{\"message\":\"ok\"}");

            client.deleteDocument("doc-1");

            assertEquals("/rag/documents/doc-1", upstream.lastUri().getPath());
        }
    }

    @Nested
    class AiChatClientImpl {

        private WebClientAiChatClient client;

        @BeforeEach
        void setUpClient() {
            client = new WebClientAiChatClient(transport);
        }

        @Test
        void sendTextPostsConditionalFieldsOnly() {
            upstream.willReturn(200, "{\"text\":\"回复\",\"confidence\":0.7}");

            ChatResponse response = client.sendText(new AiChatClient.AiChatCommand(
                    "你好", "role-1", List.of(Map.of("role", "user", "content", "hi")),
                    "ctx-1", "glm-4", "https://example.com/v1", "key", "high", "auto"));

            assertEquals(HttpMethod.POST, upstream.lastMethod());
            assertEquals("/ai/chat/text", upstream.lastUri().getPath());
            String body = upstream.lastBodyJson();
            assertTrue(body.contains("\"text\":\"你好\""));
            assertTrue(body.contains("\"role_id\":\"role-1\""));
            assertTrue(body.contains("\"model\":\"glm-4\""));
            assertTrue(body.contains("\"base_url\":\"https://example.com/v1\""));
            assertTrue(body.contains("\"api_key\":\"key\""));
            assertTrue(body.contains("\"thinking_mode\":\"high\""));
            assertTrue(body.contains("\"tool_mode\":\"auto\""));
            assertEquals("回复", response.getText());
            assertEquals(0.7, response.getConfidence());
        }

        @Test
        void sendTextOmitsBlankOptionalFields() {
            upstream.willReturn(200, "{\"text\":\"回复\"}");

            client.sendText(new AiChatClient.AiChatCommand(
                    "你好", null, null, null, " ", " ", " ", " ", null));

            String body = upstream.lastBodyJson();
            assertFalse(body.contains("model"));
            assertFalse(body.contains("base_url"));
            assertFalse(body.contains("api_key"));
            assertFalse(body.contains("thinking_mode"));
            assertFalse(body.contains("tool_mode"));
        }
    }

    @Nested
    class KnowledgeGraphClientImpl {

        private WebClientKnowledgeGraphClient client;

        @BeforeEach
        void setUpClient() {
            client = new WebClientKnowledgeGraphClient(transport);
        }

        @Test
        void buildPostsDocumentsAndUnwrapsSuccessEnvelope() {
            upstream.willReturn(200,
                    "{\"success\":true,\"data\":{\"entities_count\":10,\"triples_count\":20}}");
            KnowledgeGraphRequest.DocumentInfo doc = new KnowledgeGraphRequest.DocumentInfo();
            doc.setDocId("doc1");
            doc.setText("张三是一名律师");

            Map<String, Object> data = client.buildKnowledgeGraph(List.of(doc), "role-1");

            assertEquals("/api/knowledge-graph/build", upstream.lastUri().getPath());
            String body = upstream.lastBodyJson();
            assertTrue(body.contains("\"doc_id\":\"doc1\""));
            assertTrue(body.contains("\"role_id\":\"role-1\""));
            assertEquals(10, data.get("entities_count"));
        }

        @Test
        void nonSuccessEnvelopeYieldsEmptyMapWithoutException() {
            upstream.willReturn(200, "{\"success\":false,\"data\":null}");

            Map<String, Object> data = client.getGraphStats();

            assertTrue(data.isEmpty());
        }

        @Test
        void entityInfoUsesConcatenatedPathLikeTheFormerService() {
            upstream.willReturn(200, "{\"success\":true,\"data\":{\"name\":\"张三\"}}");

            Map<String, Object> data = client.getEntityInfo("e1", "同事", 5);

            assertEquals("/api/knowledge-graph/entity/e1", upstream.lastUri().getPath());
            String query = upstream.lastUri().getQuery();
            assertTrue(query.startsWith("relation="));
            assertTrue(query.contains("limit=5"));
            assertEquals("张三", data.get("name"));
        }

        @Test
        void graphDataReturnsEmptyMapWhenEnvelopeNotSuccessful() {
            upstream.willReturn(200, "{\"success\":false}");

            Map<String, Object> data = client.getGraphData("role-1");

            assertTrue(data.isEmpty());
        }
    }

    @Nested
    class RoleFusionClientImpl {

        private WebClientRoleFusionClient client;

        @BeforeEach
        void setUpClient() {
            client = new WebClientRoleFusionClient(transport);
        }

        @Test
        void fusePostsRoleListAndUnwrapsData() {
            upstream.willReturn(200, "{\"success\":true,\"data\":{\"fused_response\":\"综合建议\"}}");
            RoleFusionRequest request = new RoleFusionRequest();
            request.setQuestion("我想创业");
            RoleFusionRequest.RoleInfo role = new RoleFusionRequest.RoleInfo();
            role.setRoleId("lawyer");
            role.setKnowledgeDomain(List.of("法律"));
            request.setAvailableRoles(List.of(role));
            request.setRoleResponses(Map.of("lawyer", "法律建议"));

            Map<String, Object> data = client.fuseRoles(request);

            assertEquals("/ai/role-fusion/fuse", upstream.lastUri().getPath());
            String body = upstream.lastBodyJson();
            assertTrue(body.contains("\"role_id\":\"lawyer\""));
            assertTrue(body.contains("\"knowledge_domain\":[\"法律\"]"));
            assertEquals("综合建议", data.get("fused_response"));
        }
    }

    @Nested
    class TransportErrorClassification {

        private WebClientRagClient client;

        @BeforeEach
        void setUpClient() {
            client = new WebClientRagClient(transport);
        }

        @Test
        void upstream4xxClassifiesAsRejected() {
            upstream.willReturn(400, "{\"detail\":\"bad request\"}");

            PlatformAiClientException error = assertThrows(PlatformAiClientException.class,
                    () -> client.listDocuments(null));

            assertEquals(PlatformAiClientException.Type.REJECTED, error.type());
            assertEquals(400, error.upstreamStatus());
            assertTrue(error.getMessage().contains("400"));
        }

        @Test
        void upstream5xxClassifiesAsUpstreamError() {
            upstream.willReturn(503, "{\"detail\":\"down\"}");

            PlatformAiClientException error = assertThrows(PlatformAiClientException.class,
                    () -> client.listDocuments(null));

            assertEquals(PlatformAiClientException.Type.UPSTREAM_ERROR, error.type());
            assertEquals(503, error.upstreamStatus());
        }

        @Test
        void hangingUpstreamClassifiesAsTimeout() {
            upstream.willHang();

            PlatformAiClientException error = assertThrows(PlatformAiClientException.class,
                    () -> client.listDocuments(null));

            assertEquals(PlatformAiClientException.Type.TIMEOUT, error.type());
        }

        @Test
        void connectionFailureClassifiesAsUnavailable() {
            upstream.willFailWith(new WebClientRequestException(
                    new ConnectException("Connection refused"),
                    HttpMethod.POST, URI.create(BASE + "/rag/query"),
                    new org.springframework.http.HttpHeaders()));

            PlatformAiClientException error = assertThrows(PlatformAiClientException.class,
                    () -> client.listDocuments(null));

            assertEquals(PlatformAiClientException.Type.UNAVAILABLE, error.type());
        }

        @Test
        void applicationLayerNeverSeesRawTransportExceptionTypes() {
            upstream.willReturn(503, "{}");

            Throwable thrown = assertThrows(Throwable.class, () -> client.listDocuments(null));

            assertFalse(thrown instanceof org.springframework.web.reactive.function.client.WebClientException);
            assertTrue(thrown instanceof PlatformAiClientException);
        }
    }
}
