import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCN from 'element-plus/dist/locale/zh-cn.mjs'
import en from 'element-plus/dist/locale/en.mjs'

import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { initTheme } from './composables/useTheme'
import './styles/global.css'
import './styles/responsive.css'
import './styles/animations.css'

initTheme()

const app = createApp(App)
const pinia = createPinia()

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 根据当前语言设置 Element Plus 语言
const getElementPlusLocale = () => {
  const currentLocale = i18n.global.locale.value
  return currentLocale === 'en' ? en : zhCN
}

app.use(pinia)
app.use(router)
app.use(i18n)
app.use(ElementPlus, {
  locale: getElementPlusLocale()
})

app.mount('#app')

