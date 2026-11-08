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
import { currentAccount, isAuthenticated } from '@/features/auth/authService'
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

// 本机账号是入口身份的事实源：把已登录账号投影进 userStore，不再向尚未就绪的
// 后端 /user/profile 发请求。后端 N03 的 LocalIdentity 仍由平台层独立校验，不受影响。
if (isAuthenticated()) {
  const account = currentAccount()
  if (account) {
    useUserStore(pinia).setCurrentUser({
      id: account.id,
      username: account.username,
      email: account.email
    })
  }
}
app.use(router)
app.mount('#app')

