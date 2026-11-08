import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import ProjectTaskExecutionInspector from './ProjectTaskExecutionInspector.vue'
import { emptyRuntimeObservation } from '@/workbench/runtime/observation'
it('shows every persisted attempt for the selected Run without treating its latest failure as Task state', async () => {
  const observation = emptyRuntimeObservation('a')
  observation.executionTree = { run: { runId: 'a' }, nodes: [{ task: { taskId: 'task' }, attempts: [
    { attempt: { attemptId: 'first', runId: 'a', taskId: 'task', attemptNumber: 1, status: 'succeeded' }, executions: [] },
    { attempt: { attemptId: 'second', runId: 'a', taskId: 'task', attemptNumber: 2, status: 'failed' }, executions: [] },
    { attempt: { attemptId: 'foreign', runId: 'b', taskId: 'task', attemptNumber: 3, status: 'running' }, executions: [] }
  ] }] } as any
  const wrapper = mount(ProjectTaskExecutionInspector, { props: { entry: { entryId: 'task', name: 'Task', kind: 'task', taskId: 'task', status: 'completed', group: 'steps', displayOrder: 0 }, runId: 'a', runtimeObservation: observation } })
  expect(wrapper.text()).toContain('第 1 次执行 · 已完成')
  expect(wrapper.text()).toContain('第 2 次执行 · 执行失败')
  expect(wrapper.text()).not.toContain('foreign'); expect(wrapper.get('.execution-summary__status').text()).toBe('已完成')
  await wrapper.setProps({ runId: 'b' }); expect(wrapper.text()).not.toContain('second')
  expect(wrapper.text()).toContain('当前快照没有此步骤的执行历史')
  wrapper.unmount()
})
