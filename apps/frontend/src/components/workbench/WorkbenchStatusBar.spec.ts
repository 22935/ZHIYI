import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkbenchStatusBar from './WorkbenchStatusBar.vue'

const tabs = [
  { id: 'problems', label: 'Problems', count: 0, tone: 'failed' as const },
  { id: 'communication', label: 'Communication', count: 69 }
]

describe('WorkbenchStatusBar', () => {
  it('emits the selected tab and keeps zero counts free of the alert style', async () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: { tabs, modelValue: 'communication', collapsed: false }
    })

    expect(wrapper.find('.workbench-status-bar__tab.active').text()).toContain('Communication')
    expect(wrapper.findAll('.workbench-status-bar__tab-count.is-alert')).toHaveLength(0)

    await wrapper.findAll('.workbench-status-bar__tab')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['problems'])
    wrapper.unmount()
  })

  it('alerts failed-tone counts only while count > 0 and emits toggle', async () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: { tabs: [{ ...tabs[0], count: 3 }, tabs[1]], modelValue: 'problems', collapsed: true }
    })

    expect(wrapper.find('.workbench-status-bar__tab-count.is-alert').text()).toBe('3')
    expect(wrapper.find('.workbench-status-bar__toggle').attributes('aria-expanded')).toBe('false')

    await wrapper.find('.workbench-status-bar__toggle').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
    wrapper.unmount()
  })

  it('renders the left-corner run identity with a semantic status dot', () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: { tabs, modelValue: 'communication', collapsed: false, runId: 'run_8a53fc4c67e5', runStatus: 'succeeded', historical: true }
    })

    expect(wrapper.find('.workbench-status-bar__run-id').text()).toBe('Run run_8a53fc4c67e5')
    expect(wrapper.find('.workbench-status-bar__run-dot').attributes('style')).toContain('var(--sem-success)')
    expect(wrapper.find('.workbench-status-bar__run-mode').text()).toBe('read-only')
    wrapper.unmount()
  })

  it('omits the run block when no run is bound', () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: { tabs, modelValue: 'communication', collapsed: false }
    })

    expect(wrapper.find('.workbench-status-bar__run').exists()).toBe(false)
    wrapper.unmount()
  })

  it('opens the run picker, emits select-run and rerun like the VS Code branch picker', async () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: {
        tabs,
        modelValue: 'problems',
        collapsed: false,
        runId: 'run_2',
        runStatus: 'running',
        runs: [{ runId: 'run_1', status: 'succeeded' }, { runId: 'run_2', status: 'running' }],
        canRerun: true,
        rerunPending: false,
        rerunDisabledReason: '',
        rerunLabel: '再次运行'
      }
    })

    expect(wrapper.find('.workbench-status-bar__run-picker').exists()).toBe(false)
    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    expect(wrapper.find('.workbench-status-bar__run-picker').exists()).toBe(true)

    const items = wrapper.findAll('.workbench-status-bar__run-item')
    expect(items[0].text()).toContain('run_2')
    expect(items[0].classes()).toContain('is-current')
    await items[0].trigger('click')
    expect(wrapper.emitted('select-run')).toEqual([['run_2']])
    expect(wrapper.find('.workbench-status-bar__run-picker').exists()).toBe(false)

    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    await wrapper.find('.workbench-status-bar__run-action').trigger('click')
    expect(wrapper.emitted('rerun')).toHaveLength(1)
    wrapper.unmount()
  })

  it('disables rerun while the selected run is still active', async () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: {
        tabs,
        modelValue: 'problems',
        collapsed: false,
        runId: 'run_2',
        runs: [{ runId: 'run_2', status: 'running' }],
        canRerun: false,
        rerunDisabledReason: '当前运行尚未结束'
      }
    })

    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    const action = wrapper.find('.workbench-status-bar__run-action')
    expect((action.element as HTMLButtonElement).disabled).toBe(true)
    expect(action.attributes('title')).toContain('当前运行尚未结束')
    await action.trigger('click')
    expect(wrapper.emitted('rerun')).toBeUndefined()
    wrapper.unmount()
  })

  it('offers delete only for terminal runs and emits delete-run without switching selection', async () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: {
        tabs,
        modelValue: 'problems',
        collapsed: false,
        runId: 'run_2',
        runStatus: 'running',
        runs: [
          { runId: 'run_1', status: 'succeeded', canDelete: true },
          { runId: 'run_2', status: 'running' },
          { runId: 'run_3', status: 'failed', canDelete: true }
        ],
        deletingRunId: null
      }
    })

    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    // 活跃 Run（running）不出现删除按钮，终态 Run 各有一个；当前 Run 置顶后
    // 第一个删除按钮属于 run_1（succeeded）。
    const deleteButtons = wrapper.findAll('.workbench-status-bar__run-delete')
    expect(deleteButtons).toHaveLength(2)

    await deleteButtons[0].trigger('click')
    expect(wrapper.emitted('delete-run')).toEqual([['run_1']])

    // 点击删除不应触发所在行的 select-run。
    expect(wrapper.emitted('select-run')).toBeUndefined()
    wrapper.unmount()
  })

  it('disables the delete button while that run deletion is in flight', async () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: {
        tabs,
        modelValue: 'problems',
        collapsed: false,
        runId: 'run_1',
        runStatus: 'succeeded',
        runs: [{ runId: 'run_1', status: 'succeeded', canDelete: true }],
        deletingRunId: 'run_1'
      }
    })

    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    const button = wrapper.find('.workbench-status-bar__run-delete')
    expect((button.element as HTMLButtonElement).disabled).toBe(true)
    await button.trigger('click')
    expect(wrapper.emitted('delete-run')).toBeUndefined()
    wrapper.unmount()
  })

  it('renders the active file editor meta as VS Code style segments on the right', () => {
    const wrapper = mount(WorkbenchStatusBar, {
      props: { tabs, modelValue: 'communication', collapsed: false, editorStatus: { editable: true, language: 'JS', encoding: 'UTF-8', lines: 2, cursor: '行 1，列 1' } }
    })

    const segments = wrapper.findAll('.workbench-status-bar__editor-segment')
    expect(segments.map(segment => segment.text())).toEqual(['本地文件', 'JS', 'UTF-8', '2 行', '行 1，列 1'])
    // 编辑器信息在运行面板开关左侧，不再占用编辑器内部的一行。
    const rightChildren = wrapper.get('.workbench-status-bar__actions').element.children
    expect(rightChildren[0].classList.contains('workbench-status-bar__editor')).toBe(true)
    wrapper.unmount()
  })

  it('marks readonly editors and hides the editor block when no file is active', () => {
    const readonly = mount(WorkbenchStatusBar, {
      props: { tabs, modelValue: 'communication', collapsed: false, editorStatus: { editable: false, language: 'MD', encoding: 'GB18030', lines: 1, cursor: '行 1，列 1' } }
    })

    const tag = readonly.find('.workbench-status-bar__editor-segment')
    expect(tag.text()).toBe('只读')
    expect(tag.classes()).toContain('is-readonly')
    expect(tag.attributes('title')).toContain('不支持版本保护保存')
    readonly.unmount()

    const empty = mount(WorkbenchStatusBar, { props: { tabs, modelValue: 'communication', collapsed: false } })
    expect(empty.find('.workbench-status-bar__editor').exists()).toBe(false)
    empty.unmount()
  })
})
