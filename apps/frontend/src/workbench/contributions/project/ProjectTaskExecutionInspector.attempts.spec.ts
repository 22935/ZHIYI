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
  expect(wrapper.text()).toContain('Attempt 1 · succeeded · first')
  expect(wrapper.text()).toContain('Attempt 2 · failed · second')
  expect(wrapper.text()).not.toContain('foreign'); expect(wrapper.get('.execution-summary__status').text()).toBe('已完成')
  await wrapper.setProps({ runId: 'b' }); expect(wrapper.text()).not.toContain('second')
  expect(wrapper.text()).toContain('Attempt history NOT_OBSERVED')
  wrapper.unmount()
})
