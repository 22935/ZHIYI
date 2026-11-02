package com.kinlin.ai.dto.agentos;

import jakarta.validation.constraints.Min;

/** Optional optimistic revision; execution authority remains in Runtime. */
public record AgentOsRunCancelRequest(@Min(0) Long expectedRuntimeRevision) { }
