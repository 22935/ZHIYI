package com.kinlin.ai.architecture;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.JsonSerializable;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.kinlin.ai.controller.AgentOsArtifactController;
import com.kinlin.ai.controller.AgentOsMissionController;
import com.kinlin.ai.controller.AgentOsObservationController;
import com.kinlin.ai.controller.AgentOsRunController;
import com.kinlin.ai.controller.AgentOsReviewController;
import com.kinlin.ai.controller.ChatController;
import com.kinlin.ai.controller.ConversationController;
import com.kinlin.ai.controller.RoleController;
import com.kinlin.ai.controller.ChatQualityController;
import com.kinlin.ai.controller.KnowledgeGraphController;
import com.kinlin.ai.controller.RagController;
import com.kinlin.ai.controller.RoleFusionController;
import com.kinlin.ai.controller.RecommendationController;
import com.kinlin.ai.controller.AlertController;
import com.kinlin.ai.controller.AuthController;
import com.kinlin.ai.controller.FileController;
import com.kinlin.ai.controller.HealthController;
import com.kinlin.ai.controller.KylinOSController;
import com.kinlin.ai.controller.MetricsController;
import com.kinlin.ai.controller.SearchController;
import com.kinlin.ai.controller.UserProfileController;
import com.kinlin.ai.controller.UserController;
import com.kinlin.ai.entity.Conversation;
import com.kinlin.ai.entity.Message;
import com.kinlin.ai.entity.Role;
import com.kinlin.ai.entity.User;
import com.kinlin.ai.projection.message.dto.MessageQuery;
import com.kinlin.ai.projection.role.dto.RoleConfigurationQuery;
import com.kinlin.ai.projection.role.dto.RoleContextQuery;
import com.kinlin.ai.projection.role.dto.RoleQuery;
import org.junit.jupiter.api.Test;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

import java.lang.reflect.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Shared projection guards covering every controller response closure. Platform entities
 * (User, Role, Conversation, Message) are banned everywhere; the exception
 * registry is currently empty and any new raw-entity response must be registered as a
 * loan pinned to its exact GET route and raw return type, so widening the response,
 * migrating it to a projection, or rerouting it fails loudly. Strict closed-output
 * checks apply to migrated handlers only, so the dynamic POST /chat/text response stays
 * a registered follow-up scope instead of a silent pass.
 */
class QueryProjectionArchitectureTest {
    private static final Path MAIN = Path.of("src/main/java");

    private static final String RAW_MESSAGE_LIST =
            "org.springframework.http.ResponseEntity<java.util.List<com.kinlin.ai.entity.Message>>";

    /** The exact raw response still tolerated per registered handler; keep this list empty. */
    private record RawEntityResponse(String typeName, String route) { }

    private static final Map<String, RawEntityResponse> ENTITY_RESPONSE_EXCEPTIONS = Map.of();

    @Test
    void everyControllerReturnTypeRejectsPlatformEntitiesIncludingNestedBodies() throws Exception {
        Path directory = MAIN.resolve("com/kinlin/ai/controller");
        assertTrue(Files.isDirectory(directory), "backend source directory must exist; never skip this guard");
        int checked = 0;
        Set<String> remainingExceptions = new HashSet<>();
        try (Stream<Path> files = Files.list(directory)) {
            for (Path file : files.filter(path -> path.toString().endsWith(".java")).toList()) {
                Class<?> controller = Class.forName("com.kinlin.ai.controller."
                        + file.getFileName().toString().replace(".java", ""));
                if (!AnnotatedElementUtils.hasAnnotation(controller, RestController.class)) { continue; }
                for (Method method : controller.getDeclaredMethods()) {
                    if (!AnnotatedElementUtils.hasAnnotation(method, RequestMapping.class)) { continue; }
                    String handler = controller.getSimpleName() + "#" + method.getName();
                    RawEntityResponse registered = ENTITY_RESPONSE_EXCEPTIONS.get(handler);
                    if (registered != null) {
                        assertRegisteredExceptionStillMatches(handler, registered, method);
                        // Message stays tolerated for this pinned handler only; other entities remain banned.
                        assertSafe(method.getGenericReturnType(), false, new HashSet<>(), method.toString(),
                                RAW_MESSAGE_LOAN_BAN);
                        remainingExceptions.add(handler);
                        continue;
                    }
                    assertSafe(method.getGenericReturnType(), strictOutputChecked(controller, method),
                            new HashSet<>(), method.toString(), ALL_PLATFORM_ENTITIES);
                    checked++;
                }
            }
        }
        assertTrue(checked > 0, "must inspect actual HTTP handlers");
        assertEquals(ENTITY_RESPONSE_EXCEPTIONS.keySet(), remainingExceptions,
                "every registered exception must still exist; migrate the handler and shrink this list");
    }

    /**
     * A registered exception is a loan, not a free pass: the handler must still answer the
     * pinned GET route with the pinned raw entity response. Migration to a projection,
     * widening to other entities, or rerouting all invalidate the entry and must fail here.
     */
    private static void assertRegisteredExceptionStillMatches(
            String handler, RawEntityResponse registered, Method method) {
        RequestMapping mapping = AnnotatedElementUtils.findMergedAnnotation(method, RequestMapping.class);
        assertNotNull(mapping, handler + " must stay a GET route; HTTP method drift invalidates the registry");
        assertArrayEquals(new RequestMethod[]{RequestMethod.GET}, mapping.method(), handler + " must stay GET");
        RequestMapping prefix = AnnotatedElementUtils.findMergedAnnotation(
                method.getDeclaringClass(), RequestMapping.class);
        assertNotNull(prefix, handler + " must retain its controller route prefix");
        assertEquals(1, prefix.value().length, handler + " must have exactly one controller route");
        assertEquals(1, mapping.value().length, handler + " must have exactly one handler route");
        assertEquals(registered.route(), prefix.value()[0] + mapping.value()[0],
                handler + " route changed; update the registry deliberately, never by widening it");
        assertEquals(registered.typeName(), method.getGenericReturnType().getTypeName(),
                handler + " no longer answers with the pinned raw entity response; if it was migrated to a "
                        + "projection, shrink the registry (stale exception), if it widened, migrate it");
    }

    @Test
    void registeredExceptionsRejectExpansionStalenessAndRouteDrift() throws Exception {
        RawEntityResponse registered = new RawEntityResponse(RAW_MESSAGE_LIST, "/search/messages");
        assertDoesNotThrow(() -> assertRegisteredExceptionStillMatches("Fixture#valid", registered,
                ExceptionFixtures.class.getDeclaredMethod("valid")));
        assertDoesNotThrow(() -> assertRegisteredExceptionStillMatches("Fixture#alias", registered,
                ExceptionFixtures.class.getDeclaredMethod("alias")));
        assertThrows(AssertionError.class, () -> assertRegisteredExceptionStillMatches("Fixture#prefix", registered,
                ChangedPrefixFixture.class.getDeclaredMethod("valid")));
        for (String name : List.of("expanded", "stale", "rerouted", "post", "extraRoute")) {
            Method method = ExceptionFixtures.class.getDeclaredMethod(name);
            assertThrows(AssertionError.class,
                    () -> assertRegisteredExceptionStillMatches("Fixture#" + name, registered, method), name);
        }
        // Even inside a tolerated handler shape, other platform entities stay banned.
        for (String name : List.of("expanded", "wrappedConversation")) {
            Method method = ExceptionFixtures.class.getDeclaredMethod(name);
            assertThrows(AssertionError.class, () -> assertSafe(
                    method.getGenericReturnType(), false, new HashSet<>(), name,
                    RAW_MESSAGE_LOAN_BAN), name);
        }
    }

    @RequestMapping("/changed-search-prefix")
    private static class ChangedPrefixFixture {
        @GetMapping("/messages")
        ResponseEntity<List<Message>> valid() { return null; }
    }

    @RequestMapping("/search")
    private static class ExceptionFixtures {
        @GetMapping("/messages")
        ResponseEntity<List<Message>> valid() { return null; }

        @GetMapping(path = "/messages")
        ResponseEntity<List<Message>> alias() { return null; }

        @PostMapping("/messages")
        ResponseEntity<List<Message>> post() { return null; }

        @GetMapping({"/messages", "/extra"})
        ResponseEntity<List<Message>> extraRoute() { return null; }

        @GetMapping("/messages")
        ResponseEntity<List<User>> expanded() { return null; }

        @GetMapping("/messages")
        ResponseEntity<List<MessageQuery>> stale() { return null; }

        @GetMapping("/changed")
        ResponseEntity<List<Message>> rerouted() { return null; }

        @GetMapping("/wrapped")
        ResponseEntity<List<Conversation>> wrappedConversation() { return null; }
    }

    /**
     * Strict closed-output checks target migrated handlers. ChatController is strict except
     * sendTextMessage: its dynamic ChatResponse (open metadata Map) is a registered
     * follow-up scope of the chat migration, not a completed projection. The artifact
     * binary download stays a registered exact binary exception, and the same holds
     * for the unmigrated AgentOS command responses (dynamic upstream passthrough).
     */
    static boolean strictOutputChecked(Class<?> controller, Method method) {
        if (controller == UserController.class || controller == RoleController.class
                || controller == ConversationController.class || controller == SearchController.class) {
            return true;
        }
        if (controller == AgentOsMissionController.class) {
            return AnnotatedElementUtils.hasAnnotation(method, GetMapping.class);
        }
        if (controller == AgentOsRunController.class || controller == AgentOsReviewController.class) {
            return AnnotatedElementUtils.hasAnnotation(method, GetMapping.class);
        }
        if (controller == AgentOsArtifactController.class) {
            return List.of("getArtifacts", "getArtifact", "getArtifactFragments",
                    "getOutput", "getLegacyOutputs", "getResources", "getNodes", "getMaterial", "getAttachment",
                    "getResourceUsage", "getResourceHealthHistory", "getResourceCredential")
                    .contains(method.getName());
        }
        if (controller == AgentOsObservationController.class
                || controller == com.kinlin.ai.controller.AgentOsWorkspaceController.class) {
            return AnnotatedElementUtils.hasAnnotation(method, GetMapping.class);
        }
        if (controller == UserProfileController.class
                || controller == ChatQualityController.class
                || controller == RoleFusionController.class) {
            return true;
        }
        if (controller == KnowledgeGraphController.class) {
            return !"buildKnowledgeGraph".equals(method.getName());
        }
        if (controller == RagController.class) {
            return List.of("query", "listDocuments").contains(method.getName());
        }
        if (controller == RecommendationController.class) { return true; }
        if (controller == AuthController.class) { return "verifyToken".equals(method.getName()); }
        if (controller == FileController.class) { return "getFileList".equals(method.getName()); }
        if (controller == AlertController.class || controller == HealthController.class
                || controller == KylinOSController.class || controller == MetricsController.class) {
            return AnnotatedElementUtils.hasAnnotation(method, GetMapping.class);
        }
        return controller == ChatController.class && !"sendTextMessage".equals(method.getName());
    }

    @Test
    void contentValueGrammarStaysRestrictedToTheOutputBodies() throws Exception {
        // The product-body grammar (ruling 4.3) is approved for the two output DTOs
        // only; any other projection DTO embedding it fails here instead of spreading
        // the free-form exception to control metadata.
        Set<String> allowedOwners = Set.of(
                "com.kinlin.ai.projection.output.dto.OutputQuery",
                "com.kinlin.ai.projection.output.dto.LegacyOutputItemQuery",
                "com.kinlin.ai.projection.output.dto.ContentValueQuery",
                "com.kinlin.ai.projection.output.dto.ContentMemberQuery");
        Class<?> grammar = Class.forName("com.kinlin.ai.projection.output.dto.ContentValueQuery");
        Path directory = MAIN.resolve("com/kinlin/ai/projection");
        int checked = 0;
        Set<String> actualOwners = new HashSet<>();
        try (Stream<Path> files = Files.walk(directory)) {
            for (Path file : files.filter(path -> path.toString().endsWith(".java"))
                    .filter(path -> path.getParent().getFileName().toString().equals("dto")).toList()) {
                String name = MAIN.relativize(file).toString().replace('\\', '.').replace('/', '.').replace(".java", "");
                Class<?> dto = Class.forName(name);
                for (Field field : dto.getDeclaredFields()) {
                    if (Modifier.isStatic(field.getModifiers())) { continue; }
                    if (containsValueType(field.getGenericType(), grammar, new HashSet<>())) {
                        assertTrue(allowedOwners.contains(name),
                                name + "." + field.getName() + " embeds the output content grammar");
                        actualOwners.add(name);
                    }
                }
                checked++;
            }
        }
        assertTrue(checked > 0);
        assertEquals(allowedOwners, actualOwners,
                "the owner list must be updated deliberately when the grammar family changes");
    }

    private static boolean containsValueType(Type type, Class<?> grammar, Set<Type> visited) {
        if (!visited.add(type)) { return false; }
        if (type instanceof Class<?> concrete) { return concrete == grammar; }
        if (type instanceof ParameterizedType generic) {
            if (generic.getRawType() == grammar) { return true; }
            for (Type argument : generic.getActualTypeArguments()) {
                if (containsValueType(argument, grammar, visited)) { return true; }
            }
            return containsValueType(generic.getRawType(), grammar, visited);
        }
        if (type instanceof GenericArrayType array) {
            return containsValueType(array.getGenericComponentType(), grammar, visited);
        }
        return false;
    }

    @Test
    void everyProjectionDtoHasClosedTypedPublicFields() throws Exception {
        Path directory = MAIN.resolve("com/kinlin/ai/projection");
        assertTrue(Files.isDirectory(directory));
        int checked = 0;
        try (Stream<Path> files = Files.walk(directory)) {
            for (Path file : files.filter(path -> path.toString().endsWith(".java"))
                    .filter(path -> path.getParent().getFileName().toString().equals("dto")).toList()) {
                String name = MAIN.relativize(file).toString().replace('\\', '.').replace('/', '.').replace(".java", "");
                assertSafe(Class.forName(name), true, new HashSet<>(), name, ALL_PLATFORM_ENTITIES);
                checked++;
            }
        }
        assertTrue(checked > 0);
    }

    @Test
    void extensibleConfigurationCannotSpreadToOtherProjectionSlots() throws Exception {
        Path directory = MAIN.resolve("com/kinlin/ai/projection");
        assertTrue(Files.isDirectory(directory));
        try (Stream<Path> files = Files.walk(directory)) {
            for (Path file : files.filter(path -> path.toString().endsWith(".java"))
                    .filter(path -> path.getParent().getFileName().toString().equals("dto")).toList()) {
                String className = MAIN.relativize(file).toString().replace('\\', '.')
                        .replace('/', '.').replace(".java", "");
                assertConfigurationSlots(Class.forName(className));
            }
        }
    }

    @Test
    void allProjectionMappersHaveNoInfrastructureOrMutationDependencies() throws Exception {
        Path directory = MAIN.resolve("com/kinlin/ai/projection");
        assertTrue(Files.isDirectory(directory));
        int checked = 0;
        try (Stream<Path> files = Files.walk(directory)) {
            for (Path file : files.filter(path -> path.toString().endsWith(".java"))
                    .filter(path -> path.getParent().getFileName().toString().equals("mapper")).toList()) {
                String code = Files.readString(file).replaceAll("(?s)/\\*.*?\\*/", "").replaceAll("(?m)//.*$", "");
                for (String dependency : List.of("repository", "service", "gateway", "client", "infrastructure", "runtime")) {
                    assertFalse(code.contains("com.kinlin.ai." + dependency + "."), file + " depends on " + dependency);
                }
                assertFalse(java.util.regex.Pattern.compile(
                        "copyProperties\\s*\\(|convertValue\\s*\\(|@Cache|@Transactional|\\.(?:save|delete|put|remove|set\\w*)\\s*\\(")
                        .matcher(code).find(), file + " must only construct output values");
                checked++;
            }
        }
        assertTrue(checked > 0);
    }

    @Test
    void negativeFixturesDetectWrappedEntitiesDynamicDtosAndConfigurationSpread() throws Exception {
        for (String name : List.of("user", "roles", "conversations", "messages", "nested", "nestedMessage",
                "dynamic", "dynamicMetadata", "opaque", "json", "raw", "wildcard", "inherited", "getter", "checkpoint", "checkpointReference")) {
            Type type = BadResponses.class.getDeclaredMethod(name).getGenericReturnType();
            assertThrows(AssertionError.class, () -> assertSafe(type, true, new HashSet<>(), name, ALL_PLATFORM_ENTITIES), name);
        }
        assertThrows(AssertionError.class, () -> assertConfigurationSlots(ConfigurationSpread.class));
        assertThrows(AssertionError.class, () -> assertConfigurationSlots(GetterConfigurationSpread.class));
        assertDoesNotThrow(() -> assertSafe(RoleQuery.class, true, new HashSet<>(), "valid role", ALL_PLATFORM_ENTITIES));
        assertDoesNotThrow(() -> assertConfigurationSlots(RoleQuery.class));
        assertDoesNotThrow(() -> assertConfigurationSlots(RoleContextQuery.class));
        assertDoesNotThrow(() -> assertSafe(com.kinlin.ai.projection.recovery.dto.CheckpointItemQuery.class,
                true, new HashSet<>(), "public recovery reference", ALL_PLATFORM_ENTITIES));
    }

    private static final Set<Class<?>> ALL_PLATFORM_ENTITIES =
            Set.of(User.class, Role.class, Conversation.class, Message.class);

    /** A registered raw-Message loan tolerates Message only; every other platform entity stays banned. */
    private static final Set<Class<?>> RAW_MESSAGE_LOAN_BAN = buildLoanBan();

    private static Set<Class<?>> buildLoanBan() {
        Set<Class<?>> ban = new HashSet<>(ALL_PLATFORM_ENTITIES);
        ban.remove(Message.class);
        return Set.copyOf(ban);
    }

    private static void assertSafe(Type type, boolean strict, Set<Type> visited, String path,
                                   Set<Class<?>> bannedEntities) {
        if (!visited.add(type)) { return; }
        if (type instanceof ParameterizedType generic) {
            for (Type argument : generic.getActualTypeArguments()) { assertSafe(argument, strict, visited, path, bannedEntities); }
            inspectClass((Class<?>) generic.getRawType(), strict, visited, path, bannedEntities);
        } else if (type instanceof Class<?> concrete) {
            if (strict) { assertEquals(0, concrete.getTypeParameters().length, path + " contains a raw generic"); }
            inspectClass(concrete, strict, visited, path, bannedEntities);
        } else if (type instanceof GenericArrayType array) {
            assertSafe(array.getGenericComponentType(), strict, visited, path, bannedEntities);
        } else if (type instanceof WildcardType wildcard) {
            assertFalse(strict, path + " contains a wildcard");
            for (Type bound : wildcard.getUpperBounds()) { assertSafe(bound, false, visited, path, bannedEntities); }
            for (Type bound : wildcard.getLowerBounds()) { assertSafe(bound, false, visited, path, bannedEntities); }
        } else {
            assertFalse(strict, path + " contains an unresolved generic type: " + type);
        }
    }

    private static void inspectClass(Class<?> type, boolean strict, Set<Type> visited, String path,
                                     Set<Class<?>> bannedEntities) {
        for (Class<?> entity : bannedEntities) {
            assertFalse(entity.isAssignableFrom(type), path + " exposes/inherits " + entity.getSimpleName() + " Entity");
        }
        if (strict) {
            assertNotEquals(Object.class, type, path + " exposes Object");
            assertFalse(Map.class.isAssignableFrom(type), path + " exposes Map");
            assertFalse(JsonNode.class.isAssignableFrom(type), path + " exposes JsonNode");
            assertFalse(type.isAnnotationPresent(JsonSerialize.class), path + " has an unapproved serialization override");
            for (String forbidden : List.of("entity", "repository", "client", "gateway", "infrastructure", "runtime")) {
                assertFalse(type.getName().startsWith("com.kinlin.ai." + forbidden + "."), path + " references internal " + type);
            }
            assertFalse(Set.of("TaskPlan", "ACGBlueprint", "AcgBlueprint", "CompiledACGPackage",
                    "ExecutionState", "ExecutionBinding", "BindingManifest", "GraphPatch").contains(type.getSimpleName()), path);
            if (JsonSerializable.class.isAssignableFrom(type)) {
                assertEquals(RoleConfigurationQuery.class, type, path + " has an unapproved custom JSON serializer");
            }
        }
        if (type.isArray()) { assertSafe(type.getComponentType(), strict, visited, path, bannedEntities); return; }
        if (!type.getName().startsWith("com.kinlin.ai.") || type.isEnum()) { return; }
        if (type.isSealed()) {
            for (Class<?> permitted : type.getPermittedSubclasses()) { assertSafe(permitted, strict, visited, path, bannedEntities); }
        }
        for (Field field : type.getDeclaredFields()) {
            if (!Modifier.isStatic(field.getModifiers())) {
                if (strict) {
                    assertFalse(field.isAnnotationPresent(JsonSerialize.class), path + " overrides field serialization");
                    // "checkpointId" is the registered public recovery reference of the
                    // checkpoints endpoint (key set pinned by its serialization test);
                    // checkpoint snapshot data stays banned everywhere.
                    assertFalse(Set.of("passwordHash", "executionState", "checkpoint", "scheduler",
                            "binding", "executionBinding", "bindingManifest", "compiledPackage", "graphPatchRefs",
                            "sourcePatchId", "controlFrames", "resourceBindings").contains(field.getName()), field.toString());
                    if ("checkpointId".equals(field.getName())) {
                        assertEquals("com.kinlin.ai.projection.recovery.dto.CheckpointItemQuery", type.getName(),
                                path + " spreads the recovery-only public reference");
                    }
                }
                assertSafe(field.getGenericType(), strict, visited, path + "." + field.getName(), bannedEntities);
            }
        }
        for (Method method : type.getDeclaredMethods()) {
            if (strict) {
                assertFalse(method.isAnnotationPresent(JsonAnyGetter.class) || method.isAnnotationPresent(JsonAnySetter.class)
                        || method.isAnnotationPresent(JsonSerialize.class), path + " contains an open serialization method");
            }
            if (Modifier.isPublic(method.getModifiers()) && !Modifier.isStatic(method.getModifiers())
                    && method.getParameterCount() == 0 && (method.getName().startsWith("get") || method.getName().startsWith("is"))) {
                assertSafe(method.getGenericReturnType(), strict, visited, path + "." + method.getName(), bannedEntities);
            }
        }
        Type parent = type.getGenericSuperclass();
        if (parent != null && parent != Object.class) { assertSafe(parent, strict, visited, path, bannedEntities); }
    }

    private static void assertConfigurationSlots(Class<?> owner) {
        if (owner == RoleConfigurationQuery.class || owner.getEnclosingClass() == RoleConfigurationQuery.class) { return; }
        for (Field field : owner.getDeclaredFields()) {
            if (Modifier.isStatic(field.getModifiers()) || !containsConfiguration(field.getGenericType())) { continue; }
            Set<String> allowed = owner == RoleQuery.class ? Set.of("dialogueStyle", "personality", "avatarConfig")
                    : owner == RoleContextQuery.class ? Set.of("dialogueStyle", "personality") : Set.of();
            assertTrue(allowed.contains(field.getName()), "configuration spread: " + owner.getName() + "." + field.getName());
            assertEquals(RoleConfigurationQuery.class, field.getType(), "configuration cannot be a generic payload container");
        }
        for (Method method : owner.getDeclaredMethods()) {
            if (Modifier.isPublic(method.getModifiers()) && !Modifier.isStatic(method.getModifiers())
                    && method.getParameterCount() == 0 && (method.getName().startsWith("get") || method.getName().startsWith("is"))) {
                assertFalse(containsConfiguration(method.getGenericReturnType()), "configuration getter spread: " + method);
            }
        }
        for (Class<?> nested : owner.getDeclaredClasses()) { assertConfigurationSlots(nested); }
    }

    private static boolean containsConfiguration(Type type) {
        if (type instanceof Class<?> concrete) {
            return concrete == RoleConfigurationQuery.class || concrete.getEnclosingClass() == RoleConfigurationQuery.class;
        }
        if (type instanceof ParameterizedType generic) {
            return Arrays.stream(generic.getActualTypeArguments()).anyMatch(QueryProjectionArchitectureTest::containsConfiguration);
        }
        if (type instanceof GenericArrayType array) { return containsConfiguration(array.getGenericComponentType()); }
        if (type instanceof WildcardType wildcard) {
            return Stream.concat(Arrays.stream(wildcard.getUpperBounds()), Arrays.stream(wildcard.getLowerBounds()))
                    .anyMatch(QueryProjectionArchitectureTest::containsConfiguration);
        }
        return false;
    }

    private record NestedRole(Role body) { }
    private record RuntimeDto(String checkpoint) { }
    private record PrivateCheckpointReference(String checkpointId) { }
    private record DynamicDto(Map<String, String> metadata) { }
    private record WrappedMessage(Message body) { }
    private record DynamicMetadataDto(Map<String, Object> metadata) { }
    private record ConfigurationSpread(List<RoleConfigurationQuery> payload) { }
    private static class InheritedUser extends User { }
    private static class GetterDto { public Role getRole() { return null; } }
    private static class GetterConfigurationSpread { public RoleConfigurationQuery getMetadata() { return null; } }
    private interface BadResponses {
        ResponseEntity<RuntimeDto> checkpoint();
        ResponseEntity<PrivateCheckpointReference> checkpointReference();
        ResponseEntity<User> user();
        ResponseEntity<List<Role>> roles();
        ResponseEntity<List<Conversation>> conversations();
        ResponseEntity<List<Message>> messages();
        ResponseEntity<NestedRole> nested();
        ResponseEntity<WrappedMessage> nestedMessage();
        ResponseEntity<DynamicDto> dynamic();
        ResponseEntity<DynamicMetadataDto> dynamicMetadata();
        ResponseEntity<Object> opaque();
        ResponseEntity<JsonNode> json();
        ResponseEntity raw();
        ResponseEntity<? extends RoleQuery> wildcard();
        ResponseEntity<InheritedUser> inherited();
        ResponseEntity<GetterDto> getter();
    }
}
