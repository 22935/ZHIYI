package com.kinlin.ai.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Feature toggles for optional capabilities.
 */
@Data
@Component
@ConfigurationProperties(prefix = "agent.federated")
public class FeatureToggleProperties {

    private boolean enabled = false;

    private boolean trace = true;
}

