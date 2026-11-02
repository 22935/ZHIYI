package com.kinlin.ai.projection.run.mapper;

import com.kinlin.ai.projection.run.dto.*;
import com.kinlin.ai.projection.mission.dto.MissionDetailQuery;
import com.kinlin.ai.projection.mission.dto.MissionRunSummaryQuery;
import com.kinlin.ai.projection.graph.mapper.GraphProjectionMapper;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.stream.Collectors;
import static com.kinlin.ai.projection.common.mapper.QueryWire.*;

/** Explicit observation mapping; reads existing wire facts without I/O or runtime mutations. */
public final class RunProjectionMapper {
    private RunProjectionMapper() { }
    public static RunQuery run(Map<?, ?> s) {
        Map<?, ?> state = optionalObject(s.get("executionState"));
        Map<?, ?> review = optionalObject(state.get("reviewPayload"));
        List<OutputReferenceQuery> outputs = new ArrayList<>();
        Map<?, ?> refs = optionalObject(state.get("outputRefs"));
        Map<?, ?> summaries = optionalObject(state.get("outputSummaries"));
        for (var entry : refs.entrySet()) {
            if (!(entry.getKey() instanceof String key) || !(entry.getValue() instanceof String ref)) { throw invalid(); }
            outputs.add(new OutputReferenceQuery(key, ref, text(summaries, key)));
        }
        return new RunQuery(requiredText(s, "runId"), text(s, "missionId"), text(s, "title"), text(s, "workflowId"),
                text(s, "domain"), text(s, "source"), text(s, "runtimeEngine"), text(s, "status"), text(s, "lifecyclePhase"),
                text(s, "lifecycleMessage"), text(s, "currentStepId"), texts(s.get("completedStepIds")), texts(s.get("activeStepIds")),
                texts(s.get("skippedStepIds")), text(s, "outputRef"), integer(s, "runtimeRevision"), items(s.get("steps"), RunProjectionMapper::step),
                text(s, "createdAt"), text(s, "updatedAt"), text(s, "startedAt"), smallInt(state, "graphVersion"),
                new ReviewStateQuery(text(review, "subjectType"), text(review, "subjectId"), text(review, "controlId"), text(review, "stepId"),
                        text(review, "reasonCode"), smallInt(review, "iteration"), smallInt(review, "approvals"), smallInt(review, "quorum"),
                        bool(review, "accepted"), text(review, "strategy")), lineage(state), outputs,
                text(state, "planningDiversity"), integer(state, "planningSeed"), text(state, "plannerAlgorithmVersion"),
                smallInt(state, "planningCandidateCount"), text(state, "selectedPlanningVariantId"),
                s.get("formalControl") == null ? null : formalControl(object(s.get("formalControl"))),
                text(optionalObject(s.get("error")), "code"),
                RunActionCapabilitiesMapper.read(s.get("actionCapabilities"), requiredText(s, "runId"), text(s, "missionId")));
    }
    public static FormalControlQuery formalControl(Map<?, ?> c) {
        Map<?, ?> d = optionalObject(c.get("dispatch"));
        return new FormalControlQuery(requiredText(c, "status"), bool(c, "executionAuthorized"), bool(c, "permitIssued"),
                bool(c, "dispatchEligible"), bool(c, "dispatchEnabled"), text(c, "commitId"), integer(c, "commitmentRevision"),
                text(c, "materializationId"), text(c, "activationId"), text(c, "graphId"), smallInt(c, "graphVersion"),
                text(c, "handoffId"), text(c, "handoffStatus"), text(c, "permitId"), text(c, "permitStatus"),
                d.isEmpty() ? null : new FormalControlQuery.DispatchReceipt(requiredText(d, "dispatchId"), requiredText(d, "runId"),
                        requiredText(d, "permitId"), requiredInt(d, "graphVersion"), requiredText(d, "status")));
    }
    public static RunPageQuery page(Map<?, ?> s) {
        return new RunPageQuery(items(s.get("items"), RunProjectionMapper::run), integer(s, "total"), smallInt(s, "page"), smallInt(s, "pageSize"));
    }
    public static StepQuery step(Map<?, ?> s) {
        return new StepQuery(text(s, "stepId"), text(s, "name"), text(s, "agentName"), text(s, "capability"), text(s, "status"), smallInt(s, "attempt"), smallInt(s, "retryCount"), bool(s, "reviewRequired"), text(s, "outputRef"), text(s, "outputSummary"), text(s, "startedAt"), text(s, "completedAt"));
    }
    public static RunLineageQuery lineage(Map<?, ?> s) {
        return new RunLineageQuery(text(s, "parentRunId"), text(s, "sourceRunId"), text(s, "rerunReason"),
                text(s, "supersedesRunId"), text(s, "supersededByRunId"));
    }
    public static RunExecutionTreeQuery tree(Map<?, ?> s) {
        Map<?, ?> run = object(s.get("run")), blueprint = object(s.get("blueprint"));
        Map<?, ?> operational = optionalObject(s.get("operational"));
        List<TaskExecutionQuery> tasks = items(s.get("nodes"), RunProjectionMapper::taskExecution);
        Map<String, Integer> attemptNumbers = tasks.stream().flatMap(task -> task.attempts().stream())
                .collect(Collectors.toMap(detail -> detail.attempt().attemptId(),
                        detail -> detail.attempt().attemptNumber() == null ? 0 : detail.attempt().attemptNumber(), Math::max));
        List<NodeLifecycleQuery> lifecycles = new ArrayList<>();
        // Preserve the former UI ordering without exposing loop paths or execution identifiers.
        Comparator<Map<?, ?>> order = Comparator.comparingInt(node -> attemptNumbers.getOrDefault(text(node, "attemptId"), 0));
        order = order.thenComparing((left, right) -> compareLoopPath(list(left.get("loopPath")), list(right.get("loopPath"))))
                .thenComparing(node -> text(node, "executionInstanceId"), Comparator.nullsFirst(Comparator.naturalOrder()));
        for (Map<?, ?> node : list(operational.get("nodeExecutions")).stream().map(value -> object(value)).sorted(order).toList()) {
            lifecycles.add(new NodeLifecycleQuery(text(node, "stepId"), text(node, "attemptId"), text(node, "phase"),
                    text(node, "failureCode"), lifecycles.size()));
        }
        return new RunExecutionTreeQuery(new MissionRunSummaryQuery(requiredText(run, "runId"), text(run, "missionId"), text(run, "status"),
                requiredInt(run, "graphVersion"), text(run, "startedAt"), text(run, "finishedAt"), text(run, "createdAt"), text(run, "updatedAt")),
                GraphProjectionMapper.identityGraph(blueprint), tasks,
                lineage(optionalObject(operational.get("lineage"))), lifecycles);
    }
    private static int compareLoopPath(List<?> left, List<?> right) {
        for (int index = 0; index < Math.max(left.size(), right.size()); index++) {
            long a = index < left.size() ? loopIndex(left.get(index)) : -1;
            long b = index < right.size() ? loopIndex(right.get(index)) : -1;
            int difference = Long.compare(a, b);
            if (difference != 0) { return difference; }
        }
        return 0;
    }
    private static long loopIndex(Object value) {
        if (value instanceof Number number) { return new BigDecimal(number.toString()).longValueExact(); }
        throw invalid();
    }
    public static TaskExecutionQuery taskExecution(Map<?, ?> s) {
        Map<?, ?> task = object(s.get("task"));
        return new TaskExecutionQuery(new MissionDetailQuery.TaskSummary(requiredText(task, "taskId"), text(task, "missionId"),
                text(task, "semanticTaskKey"), text(task, "parentTaskId"), text(task, "title"), text(task, "objective"), text(task, "status"),
                list(task.get("constraints")).size()), text(s, "acgNodeId"), items(s.get("attempts"), RunProjectionMapper::attemptDetail));
    }
    public static AttemptDetailQuery attemptDetail(Map<?, ?> s) {
        Map<?, ?> a = object(s.get("attempt")), r = optionalObject(s.get("executionBinding"));
        return new AttemptDetailQuery(new AttemptQuery(text(a, "attemptId"), text(a, "runId"), text(a, "taskId"), text(a, "status"),
                smallInt(a, "attemptNumber"), text(a, "startedAt"), text(a, "finishedAt"), text(a, "failureReason")),
                items(s.get("executions"), e -> new StepExecutionQuery(text(e, "stepExecutionId"), text(e, "runId"), text(e, "taskId"),
                        text(e, "attemptId"), text(e, "status"), text(e, "startedAt"), text(e, "finishedAt"))),
                r.isEmpty() ? null : new ResourceUseQuery(text(r, "resourceId"), text(r, "agentId"), text(r, "modelId"), text(r, "acgNodeId"),
                        text(optionalObject(r.get("metadata")), "deploymentTier")));
    }
    public static ReviewHistoryQuery reviews(Map<?, ?> s) {
        return new ReviewHistoryQuery(text(s, "runId"), items(s.get("items"), r -> new ReviewItemQuery(text(r, "reviewId"), text(r, "runId"),
                text(r, "stepId"), text(r, "decision"), text(r, "reviewer"), text(r, "comment"), text(r, "createdAt"))), integer(s, "total"));
    }
}
