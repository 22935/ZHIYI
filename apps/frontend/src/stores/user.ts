import { defineStore } from 'pinia'
import { ref } from 'vue'
import request from '@/utils/request'

export interface User {
  id: string
  username: string
  email?: string
  avatar?: string
  createdAt?: Date | string
}

export const useUserStore = defineStore('user', () => {
  const currentUser = ref<User | null>(null)
  const loading = ref(false)
  const loadError = ref('')
  let loadedAt = 0
  let generation = 0
  let pending: Promise<void> | null = null

  const loadCurrentUser = async (options: { force?: boolean } = {}) => {
    if (!options.force && currentUser.value && Date.now() - loadedAt < 30000) return
    if (pending) return pending
    const requestGeneration = ++generation
    loading.value = true
    loadError.value = ''
    const promise = request.get<User>('/user/profile', { timeout: 10000 }).then(response => {
      if (requestGeneration !== generation) return
      if (!response.data?.id) throw new Error('本机身份尚未就绪')
      currentUser.value = response.data
      // Draft/cache scoping only; backend authority comes from LocalIdentity.
      localStorage.setItem('userId', response.data.id)
      loadedAt = Date.now()
    }).catch(error => {
      if (requestGeneration === generation) loadError.value = error.message || '本机身份加载失败'
      console.error('加载本机身份失败', error)
    }).finally(() => {
      if (pending === promise) pending = null
      if (requestGeneration === generation) loading.value = false
    })
    pending = promise
    return promise
  }

  const setCurrentUser = (user: User | null) => {
    generation += 1
    pending = null
    loading.value = false
    currentUser.value = user
    if (user) localStorage.setItem('userId', user.id)
    loadedAt = user ? Date.now() : 0
  }

  return { currentUser, loading, loadError, loadCurrentUser, setCurrentUser }
})
