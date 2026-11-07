import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElLoading, ElMessage, ElMessageBox, provideGlobalConfig } from 'element-plus'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/el-loading.css'
import zhCN from 'element-plus/dist/locale/zh-cn.mjs'
import en from 'element-plus/dist/locale/en.mjs'

import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'
import i18n from './i18n'
import { initTheme } from './composables/useTheme'
import './styles/global.css'
import './styles/responsive.css'
import './styles/animations.css'

initTheme()

const app = createApp(App)
const pinia = createPinia()

app.use(ElLoading)
app.use(ElMessage)
app.use(ElMessageBox)

// 根据当前语言设置 Element Plus 语言
const getElementPlusLocale = () => {
  const currentLocale = i18n.global.locale.value
  return currentLocale === 'en' ? en : zhCN
}

app.use(pinia)
app.use(i18n)
provideGlobalConfig({ locale: getElementPlusLocale() }, app, true)

// Restore workspace drafts only after resolving the launcher's Home identity.
void useUserStore(pinia).loadCurrentUser().finally(() => {
  app.use(router)
  app.mount('#app')
})

