import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { roleApi, type Role, type RoleCreateRequest } from '@/services/api/role'

export const useRoleStore = defineStore('role', () => {
  const builtinRoles = ref<Role[]>([])
  const customRoles = ref<Role[]>([])
  const currentRole = ref<Role | null>(null)
  const favorites = ref<string[]>([])
  const loading = ref(false)
  const rolesLoadedAt = ref(0)

  const ROLES_CACHE_TTL_MS = 30_000
  let loadBuiltinPromise: Promise<Role[]> | null = null
  let loadCustomPromise: Promise<Role[]> | null = null
  let loadRolesPromise: Promise<void> | null = null

  const roles = computed(() => [...builtinRoles.value, ...customRoles.value])

  const favoriteRoles = computed(() => {
    return roles.value.filter((r) => favorites.value.includes(r.id))
  })

  const toggleFavorite = (roleId: string) => {
    const index = favorites.value.indexOf(roleId)
    if (index === -1) {
      favorites.value.push(roleId)
    } else {
      favorites.value.splice(index, 1)
    }
    localStorage.setItem('role_favorites', JSON.stringify(favorites.value))
  }

  const loadFavorites = () => {
    const stored = localStorage.getItem('role_favorites')
    if (stored) favorites.value = JSON.parse(stored)
  }

  const loadBuiltinRoles = async (force = false) => {
    if (!force && builtinRoles.value.length > 0) return builtinRoles.value
    if (loadBuiltinPromise) return loadBuiltinPromise

    loadBuiltinPromise = roleApi
      .getBuiltinRoles()
      .then((data) => {
        builtinRoles.value = Array.isArray(data) ? data : []
        return builtinRoles.value
      })
      .catch((error) => {
        console.warn('[roleStore] loadBuiltinRoles failed:', error)
        if (!Array.isArray(builtinRoles.value)) builtinRoles.value = []
        return builtinRoles.value
      })
      .finally(() => {
        loadBuiltinPromise = null
      })

    return loadBuiltinPromise
  }

  const loadCustomRoles = async (force = false) => {
    if (!force && customRoles.value.length > 0) return customRoles.value
    if (loadCustomPromise) return loadCustomPromise

    loadCustomPromise = roleApi
      .getCustomRoles()
      .then((data) => {
        customRoles.value = Array.isArray(data) ? data : []
        return customRoles.value
      })
      .catch((error) => {
        console.warn('[roleStore] loadCustomRoles failed:', error)
        if (!Array.isArray(customRoles.value)) customRoles.value = []
        return customRoles.value
      })
      .finally(() => {
        loadCustomPromise = null
      })

    return loadCustomPromise
  }

  const loadRoles = async (force = false) => {
    const now = Date.now()
    const hasFreshCache = roles.value.length > 0 && now - rolesLoadedAt.value < ROLES_CACHE_TTL_MS
    if (!force && hasFreshCache) return
    if (!force && loadRolesPromise) return loadRolesPromise

    loadRolesPromise = (async () => {
      loading.value = true
      try {
        await Promise.all([loadBuiltinRoles(force), loadCustomRoles(force)])
        rolesLoadedAt.value = Date.now()
      } catch (error) {
        console.warn('[roleStore] loadRoles fallback after error:', error)
      } finally {
        loading.value = false
        loadRolesPromise = null
      }
    })()

    return loadRolesPromise
  }

  const selectRole = async (role: Role) => {
    currentRole.value = role
  }

  const setCurrentRole = async (role: Role) => {
    currentRole.value = role
  }

  const clearCurrentRole = () => {
    currentRole.value = null
  }

  const updateRoleAvatar = (roleId: string, avatarUrl: string) => {
    const role = roles.value.find((r) => r.id === roleId)
    if (role) {
      role.avatar = avatarUrl
    }
    if (currentRole.value && currentRole.value.id === roleId) {
      currentRole.value.avatar = avatarUrl
    }
  }

  const addRole = (role: Role) => {
    if ((role as any).isBuiltin) {
      builtinRoles.value.push(role)
    } else {
      customRoles.value.push(role)
    }
  }

  const createRole = async (request: RoleCreateRequest) => {
    loading.value = true
    try {
      const role = await roleApi.createRole(request)
      const existingIndex = customRoles.value.findIndex((r) => r.id === role.id)
      if (existingIndex === -1) {
        customRoles.value.push(role)
      } else {
        customRoles.value[existingIndex] = role
      }
      return role
    } catch (error) {
      throw error
    } finally {
      loading.value = false
    }
  }

  const updateRole = async (roleId: string, request: RoleCreateRequest) => {
    loading.value = true
    try {
      const role = await roleApi.updateRole(roleId, request)
      const index = customRoles.value.findIndex((r) => r.id === roleId)
      if (index !== -1) {
        customRoles.value[index] = role
      }
      if (currentRole.value?.id === roleId) {
        currentRole.value = role
      }
      return role
    } finally {
      loading.value = false
    }
  }

  const deleteRole = async (roleId: string) => {
    loading.value = true
    try {
      await roleApi.deleteRole(roleId)
      customRoles.value = customRoles.value.filter((r) => r.id !== roleId)
      if (currentRole.value?.id === roleId) {
        currentRole.value = null
      }
    } finally {
      loading.value = false
    }
  }

  return {
    builtinRoles,
    customRoles,
    roles,
    currentRole,
    loading,
    favorites,
    favoriteRoles,
    toggleFavorite,
    loadFavorites,
    loadBuiltinRoles,
    loadCustomRoles,
    loadRoles,
    selectRole,
    setCurrentRole,
    clearCurrentRole,
    updateRoleAvatar,
    addRole,
    createRole,
    updateRole,
    deleteRole,
  }
})
