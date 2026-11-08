import { agentosRequest } from '../client'
import type { MissionWorkspaceProjection, WorkspaceFileListing, WorkspaceFileReadResponse } from '../types'

export const createWorkspaceApi = () => ({
  async getMissionWorkspace(
    missionId: string,
    options: { runId?: string; signal?: AbortSignal } = {}
  ): Promise<MissionWorkspaceProjection> {
    const response = await agentosRequest.get<MissionWorkspaceProjection>(
      `/missions/${encodeURIComponent(missionId)}/workspace`,
      {
        params: { runId: options.runId || undefined },
        signal: options.signal
      }
    )
    return response.data
  },

  async readWorkspaceFile(missionId: string, path: string, options: { signal?: AbortSignal } = {}) {
    const response = await agentosRequest.get<WorkspaceFileReadResponse>(
      `/missions/${encodeURIComponent(missionId)}/workspace/file`,
      { params: { path }, signal: options.signal }
    )
    return response.data
  },

  async saveWorkspaceFile(missionId: string, body: {path: string; content: string; expectedVersion: string; operationId: string}) {
    const response = await agentosRequest.post<{path: string; version: string}>(
      `/missions/${encodeURIComponent(missionId)}/workspace/file`, body)
    return response.data
  },

  async listWorkspaceFiles(
    missionId: string,
    path = '.',
    options: { signal?: AbortSignal } = {}
  ): Promise<WorkspaceFileListing> {
    const response = await agentosRequest.get<WorkspaceFileListing>(
      `/missions/${encodeURIComponent(missionId)}/workspace/files`,
      { params: { path, maxEntries: 1000 }, signal: options.signal }
    )
    return response.data
  }
})
