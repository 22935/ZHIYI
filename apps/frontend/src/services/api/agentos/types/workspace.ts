import type { GraphProjection } from './graph'
import type { WorkflowStatus, RunActionCapabilities } from './workflow'
import type { InputAttachment } from './artifacts'

export type WorkspaceEntryKind = 'local_file' | 'folder' | 'graph' | 'virtual_document' | 'task' | 'artifact' | 'run' | 'progress'
export type WorkspaceIdentityQuality = 'canonical' | 'legacy'
export type WorkspaceRunStatus = WorkflowStatus | 'succeeded' | 'superseded'
export interface WorkspaceMission {
  missionId: string
  userId: string
  goal: string
  description: string
  metadata: Record<string, unknown>
  createdAt: string
  updatedAt: string
  status: string
}
export interface WorkspaceRunSummary {
  actionCapabilities?: RunActionCapabilities | null
  runId: string
  status: WorkspaceRunStatus
  parentRunId?: string | null
  sourceRunId?: string | null
  createdAt: string
  completedAt?: string | null
  isActive: boolean
}
export interface WorkspaceEntry {
  entryId: string
  kind: WorkspaceEntryKind
  name: string
  title?: string | null
  group: 'overview' | 'steps' | 'output' | 'runs' | string
  parentEntryId?: string | null
  displayOrder: number
  semanticTaskKey?: string | null
  artifactKey?: string | null
  taskId?: string | null
  logicalRole?: string | null
  objective?: string | null
  dependencyKeys?: string[]
  attemptCount?: number
  latestAttemptId?: string | null
  artifactCount?: number
  artifactId?: string | null
  contentRef?: string | null
  artifactType?: string | null
  mediaType?: string | null
  checksum?: string | null
  attemptId?: string | null
  acgNodeId?: string | null
  disposition?: 'GENERATED' | 'REUSED' | string | null
  sourceRunId?: string | null
  identityQuality?: WorkspaceIdentityQuality | null
  createdAt?: string | null
  runId?: string | null
  status?: string | null
  blueprintId?: string | null
  graphId?: string | null
  graphVersion?: number | null
  parentRunId?: string | null
  completedAt?: string | null
  isActive?: boolean | null
  content?: string | null
  metadata?: Record<string, unknown>
}
export interface WorkspaceGraphNode {
  acgNodeId: string
  nodeType: string
  name: string
  semanticTaskKey?: string | null
  taskId?: string | null
  identityQuality?: WorkspaceIdentityQuality | null
  displayOrder: number
  status?: string | null
  attemptId?: string | null
  artifactCount?: number
  artifactIds?: string[]
}
export interface WorkspaceDiagnostic {
  code: string
  message: string
  severity: 'info' | 'warning' | 'error'
  details?: Record<string, unknown>
}
export interface MissionWorkspaceProjection {
  mission: WorkspaceMission
  missionSemanticView?: {
    missionId: string
    semanticStatus: 'UNINITIALIZED' | 'INITIALIZED'
    missionRevision: number
    commitId?: string | null
    objective?: string | null
    constraints: WorkspaceSemanticConstraint[]
    sourceReferences: string[]
    sourceStatus: 'NOT_APPLICABLE' | 'UNVERIFIED'
  } | null
  missionDisplay?: {
    objective?: string | null
    sourceType: 'SEMANTIC' | 'IDENTITY_COMPATIBILITY' | 'LEGACY_INPUT' | 'LEGACY_TITLE' | 'NONE'
  } | null
  selectedRunBasis?: {
    basisSchemaVersion: number
    fingerprintVersion: number
    missionId: string
    sourceType: 'SEMANTIC' | 'LEGACY_INPUT' | 'LEGACY_TITLE'
    sourceRevision: number
    commitId?: string | null
    objective: string
    constraints: WorkspaceSemanticConstraint[]
    sourceReferences: string[]
    sourceStatus: 'NOT_APPLICABLE' | 'UNVERIFIED'
    fingerprint: string
  } | null
  selectedRunBasisStatus?: 'BOUND' | 'UNBOUND' | 'RUNTIME_UNAVAILABLE' | 'NO_RUN' | null
  activeRun?: WorkspaceRunSummary | null
  activeGraph?: GraphProjection | null
  runs: WorkspaceRunSummary[]
  entries: WorkspaceEntry[]
  graphNodes: WorkspaceGraphNode[]
  inputAttachments?: InputAttachment[]
  diagnostics: WorkspaceDiagnostic[]
}

export interface WorkspaceSemanticConstraint {
  constraintId: string
  text: string
  sourceRefs: string[]
}

export interface WorkspaceFileEntry {
  name: string
  path: string
  type: 'directory' | 'file'
}

export interface WorkspaceFileListing {
  workspaceRoot: string
  path: string
  entries: WorkspaceFileEntry[]
}

export interface WorkspaceFileOpenRequest {
  desktopWorkspaceId?: string
  missionId: string
  workspaceRoot: string
  relativePath: string
  name: string
  /** 打开后直接进入行内 diff（对比 HEAD 与当前内容）。 */
  diff?: boolean
}
