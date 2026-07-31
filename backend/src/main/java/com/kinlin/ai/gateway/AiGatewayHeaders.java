package com.kinlin.ai.gateway;

/** Header names used only on the trusted Java-to-Python hop. */
public final class AiGatewayHeaders {

    public static final String INTERNAL_SERVICE_TOKEN = "X-Internal-Service-Token";
    public static final String AUTHENTICATED_USER_ID = "X-Authenticated-User-Id";
    public static final String AUTHENTICATED_USER_SUBJECT = "X-Authenticated-User-Subject";
    public static final String AUTHENTICATED_USER_ROLE = "X-Authenticated-User-Role";
    public static final String AUTHENTICATED_TENANT_ID = "X-Authenticated-Tenant-Id";
    public static final String TRACE_ID = "X-Trace-Id";

    private AiGatewayHeaders() {
    }
}
