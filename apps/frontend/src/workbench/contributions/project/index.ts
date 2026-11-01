import { Files, FolderOpened, Search } from '@element-plus/icons-vue'
import { defineAsyncComponent } from 'vue'
import ArtifactEditor from '@/components/workspace/ArtifactEditor.vue'
import MissionEditor from '@/components/workspace/MissionEditor.vue'
import TaskEditor from '@/components/workspace/TaskEditor.vue'
import WorkspaceExplorer from '@/components/workspace/WorkspaceExplorer.vue'
import WorkspaceFileExplorer from '@/components/workbench/WorkspaceFileExplorer.vue'
import WorkspaceSearchView from '@/components/workbench/WorkspaceSearchView.vue'
import WorkspaceGitView from '@/components/workbench/WorkspaceGitView.vue'
import ProblemsPanel from '@/components/workbench/ProblemsPanel.vue'
import ProjectArtifactInspector from './ProjectArtifactInspector.vue'
import ProjectGraphInspector from './ProjectGraphInspector.vue'
import ProjectMissionInspector from './ProjectMissionInspector.vue'
import ProjectNodeInspector from './ProjectNodeInspector.vue'
import ProjectRunInspector from './ProjectRunInspector.vue'
import ProjectTaskArtifactsInspector from './ProjectTaskArtifactsInspector.vue'
import ProjectTaskExecutionInspector from './ProjectTaskExecutionInspector.vue'
import ProjectTaskIdentityInspector from './ProjectTaskIdentityInspector.vue'
import ProjectTaskResultInspector from './ProjectTaskResultInspector.vue'
import ProjectRunSidebarView from './ProjectRunSidebarView.vue'
import RunSelectionInspector from './RunSelectionInspector.vue'
import LifecycleEvidence from './LifecycleEvidence.vue'
import type { WorkbenchContribution } from '@/workbench/types'
import { workspaceDiagnostics } from '@/workbench/core/diagnostics'

const GraphEditor = Object.assign(defineAsyncComponent(() => import('@/components/workspace/GraphEditor.vue')), { name: 'GraphEditor' })
const RunProgressEditor = Object.assign(defineAsyncComponent(() => import('@/components/workspace/RunProgressEditor.vue')), { name: 'RunProgressEditor' })

export const projectContribution: WorkbenchContribution = {
  id: 'project',
  activityBar: [
    { id: 'project.activity', label: 'Projects', icon: FolderOpened, routeName: 'AcgVisualization' }
  ],
  sidebarViews: [
    { id: 'project.explorer', title: 'Explorer', component: WorkspaceExplorer }
  ],
  auxiliaryViews: [
    {
      id: 'project.workspace-files',
      title: '文件',
      order: 50,
      icon: FolderOpened,
      component: WorkspaceFileExplorer,
      when: () => true,
      getProps: context => ({ missionId: context.missionId })
    },
    {
      id: 'project.workspace-search',
      title: '搜索',
      order: 51,
      icon: Search,
      component: WorkspaceSearchView,
      when: () => true,
      getProps: context => ({ missionId: context.missionId })
    },
    {
      id: 'project.source-control',
      title: '源代码管理',
      order: 52,
      icon: Files,
      component: WorkspaceGitView,
      when: () => true,
      getProps: context => ({ missionId: context.missionId })
    }
  ],
  editors: [
    { id: 'project.graph-editor', entryKinds: ['graph'], component: GraphEditor, title: entry => entry.name },
    { id: 'project.artifact-editor', entryKinds: ['artifact'], component: ArtifactEditor, title: entry => entry.name },
    {
      id: 'project.task-editor',
      entryKinds: ['task'],
      component: TaskEditor,
      title: entry => /\.(md|markdown)$/i.test(entry.name) ? entry.name : `${entry.name}.md`
    },
    {
      id: 'project.run-progress-editor',
      entryKinds: ['progress', 'run'],
      component: RunProgressEditor,
      title: entry => entry.kind === 'run' ? `运行进度 · run-${entry.name}.md` : '运行进度 · run-progress.md'
    },
    { id: 'project.mission-editor', entryKinds: ['virtual_document'], component: MissionEditor, title: entry => entry.name }
  ],
  inspectors: [
    { id: 'project.node-inspector', component: ProjectNodeInspector, matches: context => Boolean(context.graphNode && context.entry?.kind === 'graph') },
    { id: 'project.graph-inspector', component: ProjectGraphInspector, matches: context => context.entry?.kind === 'graph' && !context.graphNode },
    { id: 'project.artifact-inspector', component: ProjectArtifactInspector, matches: context => context.entry?.kind === 'artifact' },
    { id: 'project.run-inspector', component: ProjectRunInspector, matches: context => context.entry?.kind === 'run' },
    { id: 'project.selected-node-inspector', component: ProjectNodeInspector, matches: context => Boolean(context.graphNode) },
    { id: 'project.mission-inspector', component: ProjectMissionInspector, matches: () => true }
  ],
  inspectorSections: [
    {
      id: 'project.lifecycle-evidence-section', title: 'Lifecycle', order: 80, component: LifecycleEvidence,
      when: context => context.entry?.kind === 'task' && Boolean(context.lifecycle),
      getProps: context => ({ lifecycle: context.lifecycle, observation: context.runtimeObservation })
    },
    {
      id: 'project.run-selection-section',
      title: 'Selection',
      order: 50,
      component: RunSelectionInspector,
      when: context => context.entry?.kind === 'progress' || (context.entry?.kind === 'run' && Boolean(context.selectedSymbolId))
    },
    {
      id: 'project.node-section',
      title: 'Identity',
      order: 100,
      component: ProjectNodeInspector,
      when: context => Boolean(context.graphNode) && context.entry?.kind !== 'task' && context.entry?.kind !== 'progress'
    },
    {
      id: 'project.graph-section',
      title: 'Graph',
      order: 100,
      component: ProjectGraphInspector,
      when: context => context.entry?.kind === 'graph' && !context.graphNode
    },
    {
      id: 'project.artifact-section',
      title: 'Artifact',
      order: 100,
      component: ProjectArtifactInspector,
      when: context => context.entry?.kind === 'artifact'
    },
    {
      id: 'project.task-result-section',
      title: 'Result',
      order: 90,
      component: ProjectTaskResultInspector,
      when: context => context.entry?.kind === 'task' && context.selectedSymbolType === 'result'
    },
    {
      id: 'project.task-identity-section',
      title: 'Identity',
      order: 100,
      component: ProjectTaskIdentityInspector,
      when: context => context.entry?.kind === 'task'
    },
    {
      id: 'project.task-execution-section',
      title: 'Execution',
      order: 110,
      component: ProjectTaskExecutionInspector,
      when: context => context.entry?.kind === 'task'
    },
    {
      id: 'project.task-artifacts-section',
      title: 'Artifacts',
      order: 120,
      component: ProjectTaskArtifactsInspector,
      when: context => context.entry?.kind === 'task' && context.selectedSymbolType !== 'result'
    },
    {
      id: 'project.run-section',
      title: 'Run',
      order: 100,
      component: ProjectRunInspector,
      when: context => context.entry?.kind === 'run' && !context.selectedSymbolId
    },
    {
      id: 'project.mission-section',
      title: 'Mission',
      order: 100,
      component: ProjectMissionInspector,
      when: context => !context.entry && !context.graphNode
    }
  ],
  secondarySidebarViews: [
    {
      id: 'project.run-view',
      title: '运行',
      order: 100,
      component: ProjectRunSidebarView,
      when: () => true
    }
  ],
  panels: [
    {
      id: 'problems',
      label: 'Problems',
      component: ProblemsPanel,
      tone: 'failed',
      // 角标 = Mission 投影诊断 + 最近一次静态检查结果，保证面板和底部数字一致。
      count: context => (context.runtimeObservation?.problems.length ?? context.diagnostics.length) + workspaceDiagnostics.count.value,
      getProps: context => ({ diagnostics: context.runtimeObservation?.problems || context.diagnostics, missionId: context.missionId })
    }
  ]
}
