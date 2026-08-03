package com.kinlin.ai.config;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class AgentPropertiesTest {

    @Test
    void derivesEveryRoleEndpointFromTheSharedPythonBaseUrl() {
        AgentProperties.Python python = new AgentProperties.Python();
        python.setBaseUrl("http://ai-service:8000/");

        assertThat(python.getLawyerChatUrl()).isEqualTo("http://ai-service:8000/ai/agent/lawyer/chat");
        assertThat(python.getTeacherChatUrl()).isEqualTo("http://ai-service:8000/ai/agent/teacher/chat");
        assertThat(python.getProgrammerChatUrl()).isEqualTo("http://ai-service:8000/ai/agent/programmer/chat");
        assertThat(python.getWriterChatUrl()).isEqualTo("http://ai-service:8000/ai/agent/writer/chat");
    }

    @Test
    void preservesAnExplicitRoleEndpointOverride() {
        AgentProperties.Python python = new AgentProperties.Python();
        python.setBaseUrl("http://ai-service:8000");
        python.setLawyerChatUrl(" http://legal-agent:9000/custom/chat ");

        assertThat(python.getLawyerChatUrl()).isEqualTo("http://legal-agent:9000/custom/chat");
        assertThat(python.getTeacherChatUrl()).isEqualTo("http://ai-service:8000/ai/agent/teacher/chat");
    }
}
