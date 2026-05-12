import { onMounted, ref } from 'vue'
import { useRoleStore } from '@/stores/role'

export function useDigitalHumanRole(preferredNames = ['律师', '法律']) {
  const roleStore = useRoleStore()
  const digitalHumanRoleId = ref<string>()
  const digitalHumanRoleName = ref('法律顾问')

  const resolveRole = () => {
    const matchedRole = roleStore.roles.find((role) =>
      preferredNames.some((name) => role.name?.includes(name))
    )

    if (matchedRole?.id) {
      digitalHumanRoleId.value = matchedRole.id
      digitalHumanRoleName.value = matchedRole.name || '法律顾问'
      return
    }

    digitalHumanRoleId.value = 'legal-advisor'
    digitalHumanRoleName.value = '法律顾问'
  }

  onMounted(async () => {
    try {
      await roleStore.loadRoles()
    } finally {
      resolveRole()
    }
  })

  return {
    digitalHumanRoleId,
    digitalHumanRoleName
  }
}
