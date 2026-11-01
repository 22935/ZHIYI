import type { Component } from 'vue'
import type {
  GraphProjection,
  WorkspaceDiagnostic,
  WorkspaceEntry,
  WorkspaceEntryKind,
  WorkspaceGraphNode
} from '@/services/api/agentos'
import type { RuntimeObservation } from './runtime/observation'
import type { RunDocumentSymbolType } from './runtime/runDocument'
import type { LifecycleProjection } from './runtime/lifecycleProjection'

export type WorkbenchSlot = 'activityBar' | 'sidebarViews' | 'editors' | 'inspectors' | 'inspectorSections' | 'secondarySidebarViews' | 'auxiliaryViews' | 'panels' | 'commands'

export interface WorkbenchContext {
  missionId: string
  runId: string | null
  selectedSemanticTaskKey: string | null
  selectedArtifactId: string | null
  selectedAcgNodeId: string | null
  /** Selection identity only; runtime entities remain in their projections. */
  selectedSymbolId?: string | null
  selectedSymbolType?: RunDocumentSymbolType | null
  activeEditorId: string | null
  activeEntryKind: WorkspaceEntryKind | null
  historicalMode: boolean
  diagnostics: readonly WorkspaceDiagnostic[]
  runtimeObservation: RuntimeObservation | null
  lifecycle?: LifecycleProjection
}

export interface WorkbenchInspectorContext extends WorkbenchContext {
  entry: WorkspaceEntry | null
  graphNode: WorkspaceGraphNode | null
  available: boolean
  graph: GraphProjection | null
  runStatus: string | null
}

export interface ActivityBarContribution {
  id: string
  label: string
  icon?: Component
  routeName?: string
}

export interface SidebarViewContribution {
  id: string
  title: string
  component: Component
  isVisible?: (context: WorkbenchContext) => boolean
}

export interface EditorContribution {
  id: string
  entryKinds: readonly WorkspaceEntryKind[]
  component: Component
  canOpen?: (entry: WorkspaceEntry, context: WorkbenchContext) => boolean
  title?: (entry: WorkspaceEntry, context: WorkbenchContext) => string
}

export interface InspectorContribution {
  id: string
  component: Component
  matches: (context: WorkbenchInspectorContext) => boolean
}

export interface InspectorSectionContribution {
  id: string
  title: string
  order: number
  component: Component
  when: (context: WorkbenchInspectorContext) => boolean
  getProps?: (context: WorkbenchInspectorContext) => Record<string, unknown>
}

export interface SecondarySidebarViewContribution {
  id: string
  title: string
  order: number
  component: Component
  when: (context: WorkbenchInspectorContext) => boolean
  getProps?: (context: WorkbenchInspectorContext) => Record<string, unknown>
}

export interface AuxiliaryViewContribution {
  id: string
  title: string
  order: number
  icon?: Component
  /** 图片图标（如品牌花环）；设置后触发按钮优先渲染它而非 icon 组件 */
  iconImage?: string
  component: Component
  when: (context: WorkbenchContext) => boolean
  getProps?: (context: WorkbenchContext) => Record<string, unknown>
}

export interface PanelContribution {
  id: string
  label: string
  component: Component
  count?: (context: WorkbenchContext) => number | undefined
  /** Semantic tone applied to the tab count badge while count > 0. */
  tone?: 'failed'
  isVisible?: (context: WorkbenchContext) => boolean
  getProps?: (context: WorkbenchContext) => Record<string, unknown>
}

export interface CommandContribution {
  id: string
  title: string
  execute: (context: WorkbenchContext) => void | Promise<void>
}

export interface WorkbenchContribution {
  id: string
  activityBar?: readonly ActivityBarContribution[]
  sidebarViews?: readonly SidebarViewContribution[]
  editors?: readonly EditorContribution[]
  inspectors?: readonly InspectorContribution[]
  inspectorSections?: readonly InspectorSectionContribution[]
  secondarySidebarViews?: readonly SecondarySidebarViewContribution[]
  auxiliaryViews?: readonly AuxiliaryViewContribution[]
  panels?: readonly PanelContribution[]
  commands?: readonly CommandContribution[]
}
