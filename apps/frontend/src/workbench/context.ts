import type { WorkspaceEntryKind, WorkspaceDiagnostic } from '@/services/api/agentos'
import type { RuntimeObservation } from './runtime/observation'
import type { RunDocumentSymbolType } from './runtime/runDocument'
import type { WorkbenchContext } from './types'
import type { LifecycleProjection } from './runtime/lifecycleProjection'

export interface WorkbenchContextInput {
  missionId: string
  runId?: string | null
  selectedSemanticTaskKey?: string | null
  selectedArtifactId?: string | null
  selectedAcgNodeId?: string | null
  selectedSymbolId?: string | null
  selectedSymbolType?: RunDocumentSymbolType | null
  activeEditorId?: string | null
  activeEntryKind?: WorkspaceEntryKind | null
  historicalMode?: boolean
  diagnostics?: readonly WorkspaceDiagnostic[]
  runtimeObservation?: RuntimeObservation | null
  lifecycle?: LifecycleProjection
}

export const createWorkbenchContext = (input: WorkbenchContextInput): WorkbenchContext => ({
  missionId: input.missionId,
  runId: input.runId || null,
  selectedSemanticTaskKey: input.selectedSemanticTaskKey || null,
  selectedArtifactId: input.selectedArtifactId || null,
  selectedAcgNodeId: input.selectedAcgNodeId || null,
  selectedSymbolId: input.selectedSymbolId || null,
  selectedSymbolType: input.selectedSymbolType || null,
  activeEditorId: input.activeEditorId || null,
  activeEntryKind: input.activeEntryKind || null,
  historicalMode: Boolean(input.historicalMode),
  diagnostics: input.diagnostics || [],
  runtimeObservation: input.runtimeObservation || null,
  ...(input.lifecycle ? { lifecycle: input.lifecycle } : {})
})
