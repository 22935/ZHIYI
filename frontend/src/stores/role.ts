import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { roleApi, type Role, type RoleCreateRequest } from '@/services/api/role'

export const useRoleStore = defineStore('role', () => {
  const builtinRoles = ref<Role[]>([])
  const customRoles = ref<Role[]>([])
  const currentRole = ref<Role | null>(null)
  const favorites = ref<string[]>([])
  const loading = ref(false)

  // 计算属性：所有角色
  const roles = computed(() => [...builtinRoles.value, ...customRoles.value])

  const favoriteRoles = computed(() => {
    return roles.value.filter(r => favorites.value.includes(r.id))
  })

  // 收藏/取消收藏
  const toggleFavorite = (roleId: string) => {
    const index = favorites.value.indexOf(roleId)
    if (index === -1) {
      favorites.value.push(roleId)
    } else {
      favorites.value.splice(index, 1)
    }
    // In a real app, save to localStorage or API
    localStorage.setItem('role_favorites', JSON.stringify(favorites.value))
  }

  // 加载收藏
  const loadFavorites = () => {
    const stored = localStorage.getItem('role_favorites')
    if (stored) favorites.value = JSON.parse(stored)
  }

  // 加载内置角色
  const loadBuiltinRoles = async () => {
    loading.value = true
    try {
      builtinRoles.value = await roleApi.getBuiltinRoles()
    } finally {
      loading.value = false
    }
  }

  // 加载自定义角色
  const loadCustomRoles = async () => {
    loading.value = true
    try {
      customRoles.value = await roleApi.getCustomRoles()
    } finally {
      loading.value = false
    }
  }

  // 加载所有角色
  const loadRoles = async () => {
    loading.value = true
    try {
      await Promise.all([
        loadBuiltinRoles(),
        loadCustomRoles()
      ])
    } finally {
      loading.value = false
    }
  }

  // 选择角色
  const selectRole = async (role: Role) => {
    currentRole.value = role
    // 注意：不再自动更新角色头像
    // 数字人图像由数字人组件独立管理
    // 角色的avatar字段保持不变，避免缓存问题
  }

  // 设置当前角色
  const setCurrentRole = async (role: Role) => {
    currentRole.value = role
    // 注意：不再自动更新角色头像
    // 数字人图像由数字人组件独立管理
  }
  
  // 更新角色头像（用于数字人创建成功后）
  const updateRoleAvatar = (roleId: string, avatarUrl: string) => {
    const role = roles.value.find(r => r.id === roleId)
    if (role) {
      role.avatar = avatarUrl
    }
    if (currentRole.value && currentRole.value.id === roleId) {
      currentRole.value.avatar = avatarUrl
    }
  }

  // 添加角色（用于创建后添加到列表）
  const addRole = (role: Role) => {
    if ((role as any).isBuiltin) {
      builtinRoles.value.push(role)
    } else {
      customRoles.value.push(role)
    }
  }

  // 创建自定义角色
  const createRole = async (request: RoleCreateRequest) => {
    loading.value = true
    try {
      const role = await roleApi.createRole(request)
      // 检查角色是否已存在（避免重复添加）
      const existingIndex = customRoles.value.findIndex(r => r.id === role.id)
      if (existingIndex === -1) {
        customRoles.value.push(role)
      } else {
        // 如果已存在，更新它
        customRoles.value[existingIndex] = role
      }
      return role
    } catch (error) {
      // 创建失败时，不添加到列表
      throw error
    } finally {
      loading.value = false
    }
  }

  // 更新角色
  const updateRole = async (roleId: string, request: RoleCreateRequest) => {
    loading.value = true
    try {
      const role = await roleApi.updateRole(roleId, request)
      const index = customRoles.value.findIndex(r => r.id === roleId)
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

  // 删除角色
  const deleteRole = async (roleId: string) => {
    loading.value = true
    try {
      await roleApi.deleteRole(roleId)
      customRoles.value = customRoles.value.filter(r => r.id !== roleId)
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
    updateRoleAvatar,
    addRole,
    createRole,
    updateRole,
    deleteRole
  }
})

