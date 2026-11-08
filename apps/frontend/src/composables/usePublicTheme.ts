import { computed, ref, watch } from 'vue'

/**
 * 公开介绍页与认证页的独立明暗状态。
 *
 * 工作台默认使用 codex-dark，而恢复的浅蓝白介绍页/登录页属于另一套视觉系统：
 * 若直接跟随全局 currentScheme，用户一进介绍页就会看到 darkbg.webp 的暗色版本。
 * 因此公开页默认浅色，明暗只在公开页之间共享（sessionStorage），
 * 不读写 appSettings，也不改变工作台主题。
 */
const PUBLIC_DARK_KEY = 'kinlin.public.dark.v1'

const readDark = (): boolean => {
  try {
    return sessionStorage.getItem(PUBLIC_DARK_KEY) === '1'
  } catch {
    return false
  }
}

export function usePublicTheme() {
  const dark = ref(readDark())

  watch(dark, (value) => {
    try {
      sessionStorage.setItem(PUBLIC_DARK_KEY, value ? '1' : '0')
    } catch {
      // 禁用存储时仅本次会话生效。
    }
  })

  const isDarkTheme = computed(() => dark.value)
  const themeToggleLabel = computed(() => `切换到${dark.value ? '明亮' : '黑暗'}模式`)
  const toggleTheme = () => { dark.value = !dark.value }

  return { isDarkTheme, themeToggleLabel, toggleTheme }
}
