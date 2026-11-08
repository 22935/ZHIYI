import AcgCopilotPanel from '@/components/workbench/AcgCopilotPanel.vue'
import type { WorkbenchContribution } from '@/workbench/types'

export const copilotContribution: WorkbenchContribution = {
  id: 'acg-copilot',
  auxiliaryViews: [
    {
      id: 'acg-copilot.sidebar',
      title: 'ACG Copilot',
      order: 100,
      iconImage: '/logo-mark.svg',
      component: AcgCopilotPanel,
      when: () => true
    }
  ]
}
