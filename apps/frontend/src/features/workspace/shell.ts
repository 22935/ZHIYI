import type { InjectionKey, Ref } from 'vue'

export type WorkspaceSurface = 'workbench' | 'oscode'
export type WorkbenchSidebar = 'thought' | 'files' | 'search' | 'git'

export const workbenchSidebarViews: Record<Exclude<WorkbenchSidebar, 'thought'>, string> = {
  files: 'project.workspace-files',
  search: 'project.workspace-search',
  git: 'project.source-control'
}

export interface WorkspaceShell {
  activeSidebar: Readonly<Ref<WorkbenchSidebar>>
  sidebarActivation: Readonly<Ref<number>>
  switching: Readonly<Ref<boolean>>
  switchSurface: (surface: WorkspaceSurface) => Promise<void>
}

export const workspaceShellKey: InjectionKey<WorkspaceShell> = Symbol('workspace-shell')
