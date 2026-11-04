import { projectRunLifecycle } from '@/features/workspace/runLifecycle'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentOsRunSummaryCard from './AgentOsRunSummaryCard.vue'
import type { WorkflowProgress, WorkflowRun } from '@/services/api/workflow'

const progress: WorkflowProgress = {
  taskId: 'task_1', runId: 'run_1', workflowId: 'workflow_1', status: 'running',
  phase: 'executing', message: 'running', percent: 50, totalSteps: 4, pendingSteps: 1,
  runningSteps: 1, waitingReviewSteps: 0, retryingSteps: 0, failedSteps: 0,
  completedSteps: 2, cancelledSteps: 0, currentStepId: 'step_3', activeStepIds: ['step_3'],
  startedAt: '2026-08-19T00:00:00Z', updatedAt: '2026-08-19T00:01:00Z', progress: 0.5, percentage: 50
}

const run: WorkflowRun = {
  runId: 'run_1', taskId: 'task_1', workflowId: 'workflow_1', domain: 'native', status: 'running',
  steps: [], skippedStepIds: ['step_2'], graphVersion: 3
}

describe('AgentOsRunSummaryCard', () => {
  it('projects only 执行运行时 v2 run, graph and audit facts', () => {
    const wrapper = mount(AgentOsRunSummaryCard, {
      props: {
        progress,
        run,
        view: {
          runId:'run_1', status: 'running', graphVersion: 3, stepStates: [], interactions: [{ interactionId: 'i1' }],
          recoveryTrace: [], scheduleTrace: [], contractViolations: [], lowEntropyMetrics: { recoveryCount: 2 }
        } as any,
        events: [{ eventId: 'event_1', runId: 'run_1', eventType: 'STEP_STARTED' }]
      }
    })
    expect(wrapper.text()).toContain('运行态摘要')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).not.toContain('GraphPatch 引用')
    expect(wrapper.text()).toContain('2 次恢复')
    expect(wrapper.text()).not.toContain('bindingSwitchCount')
    expect(wrapper.text()).not.toContain('Runtime Graph')
  })

  it('renders an honest empty state instead of invented metrics', () => {
    const wrapper = mount(AgentOsRunSummaryCard)
    expect(wrapper.text()).toContain('—')
    expect(wrapper.text()).toContain('等待可验证的运行审计事件')
  })
  it.each(['both','progress-only','foreign-progress','revision','completed','new-run','stale-view'])('renders the supplied verified lifecycle for %s', kind => {
    const selected = kind === 'new-run' ? 'run_2':'run_1'
    const detail = kind === 'progress-only' ? null : { ...run, missionId:'mission',runId:selected,runtimeRevision:4,status:kind==='completed'?'completed':'running' }
    const observation = { ...progress, missionId:kind==='foreign-progress'?'foreign':'mission',runId:selected,runtimeRevision:kind==='revision'?5:4 }
    const lifecycle = projectRunLifecycle({ missionId:'mission',runId:selected,run:detail,progress:observation })
    const wrapper=mount(AgentOsRunSummaryCard,{props:{run:detail,progress:observation,lifecycle,view:{runId:'old',status:'failed'} as any} as any})
    expect(wrapper.get('.status').text()).toBe(lifecycle.phaseLabel)
    if(kind==='progress-only') expect(wrapper.get('.status').text()).toBe('执行中')
    if(kind==='completed') expect(wrapper.get('.status').text()).toBe('已完成')
    wrapper.unmount()
  })

  it('does not substitute conflicting Progress counters for missing Run evidence', () => {
    const detail = { ...run, missionId:'mission', status:'completed', runtimeRevision:4,
      steps:[], activeStepIds:undefined, skippedStepIds:undefined } as any
    const observation = { ...progress, missionId:'mission', status:'running', runtimeRevision:4,
      totalSteps:7, completedSteps:3, activeStepIds:['stale-step'] } as any
    const lifecycle = projectRunLifecycle({ missionId:'mission', runId:'run_1', run:detail, progress:observation })
    const wrapper = mount(AgentOsRunSummaryCard, { props:{ run:detail, progress:observation, lifecycle } as any })
    expect(wrapper.get('.status').text()).toBe('已完成')
    expect(wrapper.text()).toContain('Progress 观测与 Run 状态冲突，已隔离待核对。')
    const values = wrapper.findAll('.summary-grid > div').map(item => item.get('b').text())
    expect(values.slice(1,6)).toEqual(['—','—','—','—','—'])
    wrapper.unmount()
  })

})
