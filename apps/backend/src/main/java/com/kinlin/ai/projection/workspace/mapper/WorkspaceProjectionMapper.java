package com.kinlin.ai.projection.workspace.mapper;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.time.OffsetDateTime;
import java.time.DateTimeException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.kinlin.ai.projection.graph.mapper.GraphProjectionMapper;
import com.kinlin.ai.projection.workspace.dto.MissionWorkspaceQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceAttachmentQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceDiagnosticDetailsQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceDiagnosticQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceEntryMetadataQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceEntryQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceGraphNodeQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceGraphQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceMissionQuery;
import com.kinlin.ai.projection.workspace.dto.WorkspaceRunSummaryQuery;
import com.kinlin.ai.projection.run.mapper.RunActionCapabilitiesMapper;

import static com.kinlin.ai.projection.common.mapper.QueryWire.bool;
import static com.kinlin.ai.projection.common.mapper.QueryWire.invalid;
import static com.kinlin.ai.projection.common.mapper.QueryWire.items;
import static com.kinlin.ai.projection.common.mapper.QueryWire.object;
import static com.kinlin.ai.projection.common.mapper.QueryWire.optionalObject;
import static com.kinlin.ai.projection.common.mapper.QueryWire.requiredText;
import static com.kinlin.ai.projection.common.mapper.QueryWire.smallInt;
import static com.kinlin.ai.projection.common.mapper.QueryWire.text;
import static com.kinlin.ai.projection.common.mapper.QueryWire.texts;

/**
 * Pure whitelist mapping from the MissionWorkspaceProjection wire (agentos_v2.py) to the
 * typed Workspace DTOs. No I/O, no state, no upstream mutation.
 *
 * <p>METADATA COMPATIBILITY RULES (E1 review 15db91e7: descriptor metadata reaches this
 * wire through canonicalization, and the frontend readers accept numbers and booleans —
 * String-only filtering is NOT display-equivalent). Each whitelisted key follows its
 * verified consumer, verified against the real frontend reader functions:
 * <ul>
 *   <li>{@code outputRef}/{@code outputSummary} — TaskEditor has typeof-string guards.
 *       {@code runtimeStatus} has a string-typed producer; ProjectTaskExecutionInspector
 *       uses String(value || fallback), not a typeof guard. These fields accept strings
 *       only; arbitrary metadata values outside the producer contract are omitted.</li>
 *   <li>{@code artifactKind}/{@code artifact_kind}/{@code schema}/{@code schemaName}/
 *       {@code confidence} — artifactProjection {@code text()} renders strings verbatim,
 *       finite numbers and booleans as display strings, and everything else as empty;
 *       the mapper mirrors exactly that: String verbatim, finite number/boolean to its
 *       display string (JS Number formatting, integral doubles collapse to integers),
 *       objects/arrays/null omitted — never stringified.</li>
 *   <li>{@code agentName}/{@code agent} — runDocument {@code safeText()} accepts strings
 *       and numbers but nulls booleans, so booleans are omitted here while numbers map.</li>
 *   <li>Reference lists — artifactProjection {@code list()} filters per element, so one
 *       bad member never discards the valid ones: arrays map per element with the scalar
 *       rule and drop non-scalars; non-arrays render empty upstream and are omitted.</li>
 *   <li>Non-finite numbers (NaN/Infinity) are displayable in no reader and cannot survive
 *       the gateway's standard JSON parser; as direct mapper input they are omitted, never
 *       stringified into "NaN" tokens.</li>
 *   <li>{@code taskPlanVersion} — public plan versions are exact integers; null, integers
 *       and integer strings map exactly, while fractional/overflow/object values are the
 *       abnormal-pointer case: the field is omitted, the diagnostic (and the workspace)
 *       stays usable, and the raw value is never echoed.</li>
 * </ul>
 *
 * <p>The single system-generated virtual document ({@code overview:mission.md}) is rebuilt
 * from whitelisted public facts on this wire; its upstream body embeds internal mission
 * metadata and plan constraint specs that must not reach the response. Every other entry's
 * content passes through byte-for-byte. Structural fields keep the strict QueryWire rules:
 * a wrong-typed structural value fails the contract loudly (502 envelope), never a silent
 * fabrication.
 */
public final class WorkspaceProjectionMapper {
    private WorkspaceProjectionMapper() { }

    public static MissionWorkspaceQuery workspace(Map<String, Object> wire) {
        for (String field : List.of("runs", "entries", "graphNodes", "inputAttachments", "diagnostics")) {
            if (!(wire.get(field) instanceof List<?>)) { throw invalid(); }
        }
        WorkspaceMissionQuery mission = mission(object(wire.get("mission")));
        WorkspaceRunSummaryQuery activeRun =
                wire.get("activeRun") == null ? null : runSummary(object(wire.get("activeRun")), mission.missionId());
        WorkspaceGraphQuery activeGraph =
                wire.get("activeGraph") == null ? null : graph(object(wire.get("activeGraph")));
        List<WorkspaceAttachmentQuery> attachments =
                items(wire.get("inputAttachments"), WorkspaceProjectionMapper::attachment);
        List<WorkspaceEntryQuery> entries = items(wire.get("entries"), WorkspaceProjectionMapper::entry);
        if (entries.stream().anyMatch(WorkspaceProjectionMapper::isSystemDocument)) {
            String document = missionDocument(mission, activeRun, entries, attachments);
            entries = entries.stream()
                    .map(entry -> isSystemDocument(entry) ? withContent(entry, document) : entry)
                    .toList();
        }
        return new MissionWorkspaceQuery(mission, activeRun, activeGraph,
                items(wire.get("runs"), row -> runSummary(row, mission.missionId())), entries,
                items(wire.get("graphNodes"), WorkspaceProjectionMapper::graphNode), attachments,
                items(wire.get("diagnostics"), WorkspaceProjectionMapper::diagnostic));
    }

    private static WorkspaceMissionQuery mission(Map<?, ?> raw) {
        return new WorkspaceMissionQuery(requiredText(raw, "missionId"), requiredText(raw, "goal"),
                text(raw, "description"), requiredText(raw, "status"),
                time(raw, "createdAt", false), time(raw, "updatedAt", false));
    }

    private static WorkspaceRunSummaryQuery runSummary(Map<?, ?> raw, String missionId) {
        Boolean isActive = bool(raw, "isActive");
        if (isActive == null) { throw invalid(); }
        return new WorkspaceRunSummaryQuery(requiredText(raw, "runId"), requiredText(raw, "status"),
                text(raw, "parentRunId"), text(raw, "sourceRunId"),
                time(raw, "createdAt", false), time(raw, "completedAt", true), isActive,
                RunActionCapabilitiesMapper.read(raw.get("actionCapabilities"), requiredText(raw, "runId"), missionId));
    }

    /** Blueprint display graph; node/edge/display rules are the run graph mapper's own. */
    private static WorkspaceGraphQuery graph(Map<?, ?> raw) {
        return new WorkspaceGraphQuery(requiredText(raw, "graphId"), smallInt(raw, "graphVersion"),
                text(raw, "missionId"), planVersion(raw.get("taskPlanVersion")), text(raw, "objective"),
                text(raw, "complexityLevel"), items(raw.get("nodes"), GraphProjectionMapper::node),
                items(raw.get("edges"), GraphProjectionMapper::edge));
    }

    private static WorkspaceGraphNodeQuery graphNode(Map<?, ?> raw) {
        return new WorkspaceGraphNodeQuery(requiredText(raw, "acgNodeId"), requiredText(raw, "nodeType"),
                requiredText(raw, "name"), text(raw, "semanticTaskKey"), text(raw, "taskId"),
                text(raw, "identityQuality"), nonNegativeInt(raw, "displayOrder"), text(raw, "status"),
                text(raw, "attemptId"), nonNegativeInt(raw, "artifactCount"), texts(raw.get("artifactIds")));
    }

    private static WorkspaceAttachmentQuery attachment(Map<?, ?> raw) {
        return new WorkspaceAttachmentQuery(requiredText(raw, "attachmentId"), requiredText(raw, "originalFilename"),
                requiredText(raw, "mimeType"), requiredText(raw, "extension"), nonNegativeLong(raw, "sizeBytes"),
                requiredText(raw, "sha256"), requiredText(raw, "status"), text(raw, "extractedContentRef"),
                nonNegativeLong(raw, "characterCount"), text(raw, "parser"), text(raw, "parseError"),
                time(raw, "createdAt", false), time(raw, "updatedAt", false));
    }

    private static WorkspaceEntryQuery entry(Map<?, ?> raw) {
        return new WorkspaceEntryQuery(
                requiredText(raw, "entryId"), requiredText(raw, "kind"), requiredText(raw, "name"),
                requiredText(raw, "group"), text(raw, "title"), text(raw, "parentEntryId"),
                nonNegativeInt(raw, "displayOrder"), text(raw, "semanticTaskKey"), text(raw, "artifactKey"),
                text(raw, "taskId"), text(raw, "logicalRole"), text(raw, "objective"),
                texts(raw.get("dependencyKeys")), nonNegativeInt(raw, "attemptCount"),
                text(raw, "latestAttemptId"), nonNegativeInt(raw, "artifactCount"), text(raw, "artifactId"),
                text(raw, "contentRef"), text(raw, "artifactType"), text(raw, "mediaType"), text(raw, "checksum"),
                text(raw, "attemptId"), text(raw, "acgNodeId"), text(raw, "disposition"), text(raw, "sourceRunId"),
                text(raw, "identityQuality"), time(raw, "createdAt", true), text(raw, "runId"), text(raw, "status"),
                text(raw, "blueprintId"), text(raw, "graphId"), smallInt(raw, "graphVersion"),
                text(raw, "parentRunId"), time(raw, "completedAt", true), bool(raw, "isActive"),
                text(raw, "content"), metadata(optionalObject(raw.get("metadata"))));
    }

    private static WorkspaceEntryMetadataQuery metadata(Map<?, ?> raw) {
        return new WorkspaceEntryMetadataQuery(
                strictText(raw.get("outputRef")), strictText(raw.get("outputSummary")),
                strictText(raw.get("runtimeStatus")), planVersion(raw.get("taskPlanVersion")),
                displayScalar(raw.get("artifactKind")), displayScalar(raw.get("artifact_kind")),
                displayScalar(raw.get("schema")), displayScalar(raw.get("schemaName")),
                displayList(raw.get("evidenceRefs")), displayList(raw.get("evidence_refs")),
                displayList(raw.get("upstreamInputs")), displayList(raw.get("sourceStepIds")),
                displayList(raw.get("traceLinks")), displayList(raw.get("traceRefs")),
                displayScalar(raw.get("confidence")), agentDisplay(raw.get("agentName")),
                agentDisplay(raw.get("agent")));
    }

    /** String-only reference/summary consumers and the string-typed runtime status producer. */
    private static String strictText(Object value) {
        return value instanceof String text ? text : null;
    }

    /** artifactProjection text() display semantics: strings, finite numbers, booleans only. */
    private static String displayScalar(Object value) {
        if (value instanceof String display) { return display; }
        if (value instanceof Boolean flag) { return String.valueOf(flag); }
        if (value instanceof Number number) {
            double raw = number.doubleValue();
            if (!Double.isFinite(raw)) { return null; }
            return numberDisplay(raw);
        }
        return null; // objects/arrays/null render empty upstream — omitted, never stringified
    }

    /** Shortest binary64 round-trip decimal, with ECMAScript's notation thresholds. */
    private static String numberDisplay(double value) {
        if (value == 0) { return "0"; }
        double magnitude = Math.abs(value);
        BigDecimal exact = new BigDecimal(magnitude);
        BigDecimal shortest = null;
        for (int precision = 1; precision <= 17 && shortest == null; precision++) {
            for (RoundingMode rounding : List.of(RoundingMode.DOWN, RoundingMode.UP)) {
                BigDecimal candidate = exact.round(new MathContext(precision, rounding)).stripTrailingZeros();
                if (candidate.doubleValue() != magnitude) { continue; }
                if (shortest == null) {
                    shortest = candidate;
                } else {
                    int distance = candidate.subtract(exact).abs().compareTo(shortest.subtract(exact).abs());
                    if (distance < 0 || (distance == 0 && !candidate.unscaledValue().testBit(0))) {
                        shortest = candidate;
                    }
                }
            }
        }
        if (shortest == null) { throw invalid(); }
        int exponent = shortest.precision() - shortest.scale() - 1;
        String display;
        if (exponent >= -6 && exponent < 21) {
            display = shortest.toPlainString();
        } else {
            String digits = shortest.unscaledValue().toString();
            String coefficient = digits.length() == 1 ? digits : digits.charAt(0) + "." + digits.substring(1);
            display = coefficient + "e" + (exponent >= 0 ? "+" : "") + exponent;
        }
        return value < 0 ? "-" + display : display;
    }

    /** runDocument safeText() accepts strings and numbers but nulls booleans. */
    private static String agentDisplay(Object value) {
        return value instanceof Boolean ? null : displayScalar(value);
    }

    /** list() filters per element, so valid members survive a bad one; non-arrays render empty. */
    private static List<String> displayList(Object value) {
        if (!(value instanceof List<?> raw)) { return null; }
        return raw.stream().map(WorkspaceProjectionMapper::displayScalar)
                .filter(member -> member != null).toList();
    }

    /** Exact public plan version; abnormal pointers are omitted, never echoed. */
    private static Integer planVersion(Object value) {
        if (value == null) { return null; }
        if (value instanceof Number number) {
            double raw = number.doubleValue();
            if (!Double.isFinite(raw) || raw != Math.rint(raw)) { return null; }
            try { return new BigDecimal(number.toString()).intValueExact(); }
            catch (ArithmeticException overflow) { return null; }
        }
        if (value instanceof String text && text.matches("-?\\d+")) {
            try { return Integer.valueOf(text); }
            catch (NumberFormatException overflow) { return null; }
        }
        return null;
    }

    private static WorkspaceDiagnosticQuery diagnostic(Map<?, ?> raw) {
        String code = requiredText(raw, "code");
        return new WorkspaceDiagnosticQuery(code, requiredText(raw, "message"), requiredText(raw, "severity"),
                detailsFor(code, optionalObject(raw.get("details"))));
    }

    /** Per-code field whitelist; unknown codes keep code/message/severity with empty details. */
    private static WorkspaceDiagnosticDetailsQuery detailsFor(String code, Map<?, ?> details) {
        return switch (code) {
            case "RUN_DELIVERABLE_MISSING" -> new WorkspaceDiagnosticDetailsQuery(
                    text(details, "runId"), null, null, null, null, null, null, null, null);
            case "GRAPH_TASK_NOT_FOUND" -> new WorkspaceDiagnosticDetailsQuery(
                    null, text(details, "acgNodeId"), text(details, "taskId"), null, null, null, null, null, null);
            case "TASK_PLAN_TASK_NOT_FOUND" -> new WorkspaceDiagnosticDetailsQuery(
                    text(details, "runId"), null, null, text(details, "semanticTaskKey"), null, null, null, null, null);
            case "LEGACY_ARTIFACT_IDENTITY" -> new WorkspaceDiagnosticDetailsQuery(
                    null, null, null, null, nonNegativeLong(details, "count"), null, null, null, null);
            case "PLAN_SNAPSHOT_UNRESOLVED" -> new WorkspaceDiagnosticDetailsQuery(
                    text(details, "runId"), null, null, null, null, planVersion(details.get("taskPlanVersion")),
                    null, null, null);
            case "PLANNING_PROJECTION_PENDING" -> new WorkspaceDiagnosticDetailsQuery(
                    null, null, null, null, null, null, text(details, "runtimeStatus"),
                    text(details, "lifecyclePhase"), text(details, "errorCode"));
            default -> new WorkspaceDiagnosticDetailsQuery(
                    null, null, null, null, null, null, null, null, null);
        };
    }

    private static boolean isSystemDocument(WorkspaceEntryQuery entry) {
        return "overview:mission.md".equals(entry.entryId()) && "virtual_document".equals(entry.kind());
    }

    private static WorkspaceEntryQuery withContent(WorkspaceEntryQuery entry, String content) {
        return new WorkspaceEntryQuery(entry.entryId(), entry.kind(), entry.name(), entry.group(),
                entry.title(), entry.parentEntryId(), entry.displayOrder(), entry.semanticTaskKey(),
                entry.artifactKey(), entry.taskId(), entry.logicalRole(), entry.objective(),
                entry.dependencyKeys(), entry.attemptCount(), entry.latestAttemptId(), entry.artifactCount(),
                entry.artifactId(), entry.contentRef(), entry.artifactType(), entry.mediaType(),
                entry.checksum(), entry.attemptId(), entry.acgNodeId(), entry.disposition(), entry.sourceRunId(),
                entry.identityQuality(), entry.createdAt(), entry.runId(), entry.status(), entry.blueprintId(),
                entry.graphId(), entry.graphVersion(), entry.parentRunId(), entry.completedAt(),
                entry.isActive(), content, entry.metadata());
    }

    /**
     * Rebuild of the upstream {@code _mission_document} body from whitelisted public facts:
     * identical section structure and key names minus the internal "Mission metadata"
     * section and the plan "Constraints:" lines. Steps come from the task entries of this
     * wire, so plan nodes without a resolvable task are never fabricated.
     */
    private static String missionDocument(WorkspaceMissionQuery mission, WorkspaceRunSummaryQuery activeRun,
            List<WorkspaceEntryQuery> entries, List<WorkspaceAttachmentQuery> attachments) {
        List<String> lines = new ArrayList<>();
        lines.add("# " + mission.goal());
        if (mission.description() != null && !mission.description().isEmpty()) {
            lines.add("");
            lines.add(mission.description());
        }
        lines.add("");
        lines.add("## Current Run");
        if (activeRun == null) {
            lines.add("No Run has been created.");
        } else {
            lines.add("- Run: `" + activeRun.runId() + "`");
            lines.add("- Status: `" + activeRun.status() + "`");
            if (activeRun.completedAt() != null) {
                lines.add("- Completed: `" + activeRun.completedAt() + "`");
            }
        }
        lines.add("");
        lines.add("## Input attachments");
        if (attachments.isEmpty()) {
            lines.add("No input attachments.");
        } else {
            for (WorkspaceAttachmentQuery attachment : attachments) {
                lines.add("- **" + attachment.originalFilename() + "** (`" + attachment.attachmentId() + "`) - "
                        + attachment.status() + ", " + attachment.sizeBytes() + " bytes, `" + attachment.sha256() + "`");
            }
        }
        List<WorkspaceEntryQuery> tasks = entries.stream()
                .filter(entry -> "task".equals(entry.kind())).toList();
        if (!tasks.isEmpty()) {
            lines.add("");
            lines.add("## Planned steps");
            for (WorkspaceEntryQuery task : tasks) {
                if (task.semanticTaskKey() == null) { throw invalid(); }
                lines.add("- **" + task.name() + "** (`" + task.semanticTaskKey() + "`)"
                        + (task.objective() == null ? "" : ": " + task.objective()));
            }
        }
        return String.join("\n", lines) + "\n";
    }

    private static String time(Map<?, ?> source, String field, boolean optional) {
        String value = optional ? text(source, field) : requiredText(source, field);
        if (value != null) {
            try { OffsetDateTime.parse(value); }
            catch (DateTimeException invalidTime) { throw invalid(); }
        }
        return value; // Preserve upstream offset and precision instead of reformatting it.
    }

    private static int nonNegativeInt(Map<?, ?> source, String field) {
        if (!(source.get(field) instanceof Number value)) { throw invalid(); }
        int result = new BigDecimal(value.toString()).intValueExact();
        if (result < 0) { throw invalid(); }
        return result;
    }

    private static long nonNegativeLong(Map<?, ?> source, String field) {
        if (!(source.get(field) instanceof Number value)) { throw invalid(); }
        BigDecimal exact = value instanceof Float || value instanceof Double
                ? new BigDecimal(value.doubleValue()) : new BigDecimal(value.toString());
        long result = exact.longValueExact();
        if (result < 0) { throw invalid(); }
        return result;
    }
}
