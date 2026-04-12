<template>
  <div class="login-view">
    <!-- Atmospheric Background -->
    <div class="ambient-glow top-left"></div>
    <div class="ambient-glow bottom-right"></div>
    
    <div class="login-container glass-panel">
      <!-- Left side: Brand/Promo -->
      <div class="promo-side">
        <div class="promo-content">
          <div class="brand">
            <div class="logo-box">K</div>
            <span class="brand-name">Kinlin AI</span>
          </div>
          
          <div class="hero-text">
            <h1 class="title">智能数字人交互</h1>
            <p class="subtitle">开启全感知、沉浸式的 AI 对话新纪元</p>
          </div>
          
          <div class="visual-area">
            <!-- <div class="dh-aura">
              <el-icon class="dh-icon"><UserFilled /></el-icon>
              <div class="aura-ring ring-1"></div>
              <div class="aura-ring ring-2"></div>
            </div> -->
          </div>
          
          <div class="badges">
            <div class="badge-item">
              <el-icon><Monitor /></el-icon>
              <span>多端同步</span>
            </div>
            <div class="badge-item">
              <el-icon><Connection /></el-icon>
              <span>实时交互</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Right side: Auth Form -->
      <div class="auth-side">
        <div class="auth-content">
          <el-tabs v-model="activeTab" class="premium-tabs">
            <el-tab-pane label="登录" name="login">
              <div class="auth-header">
                <h2>欢迎回来</h2>
                <p>请输入您的凭据以访问您的帐户</p>
              </div>
              
              <el-form
                ref="loginFormRef"
                :model="loginForm"
                :rules="loginRules"
                label-width="0"
                class="auth-form"
              >
                <el-form-item prop="username">
                  <el-input
                    v-model="loginForm.username"
                    placeholder="用户名"
                    :prefix-icon="User"
                    class="premium-input"
                  />
                </el-form-item>
                
                <el-form-item prop="password">
                  <el-input
                    v-model="loginForm.password"
                    type="password"
                    placeholder="密码"
                    :prefix-icon="Lock"
                    show-password
                    class="premium-input"
                    @keyup.enter="handleLogin"
                  />
                </el-form-item>
                
                <div class="form-options">
                  <el-checkbox v-model="loginForm.remember">记住我</el-checkbox>
                  <el-button link class="forgot-link">忘记密码？</el-button>
                </div>
                
                <el-button
                  type="primary"
                  class="submit-btn"
                  @click="handleLogin"
                  :loading="loading"
                >
                  登录
                </el-button>
              </el-form>
            </el-tab-pane>
            
            <el-tab-pane label="注册" name="register">
              <div class="auth-header">
                <h2>创建帐户</h2>
                <p>开启您的 AI 探索之旅</p>
              </div>
              
              <el-form
                ref="registerFormRef"
                :model="registerForm"
                :rules="registerRules"
                label-width="0"
                class="auth-form"
              >
                <el-form-item prop="username">
                  <el-input
                    v-model="registerForm.username"
                    placeholder="用户名"
                    :prefix-icon="User"
                    class="premium-input"
                  />
                </el-form-item>
                
                <el-form-item prop="email">
                  <el-input
                    v-model="registerForm.email"
                    placeholder="邮箱"
                    :prefix-icon="Message"
                    class="premium-input"
                  />
                </el-form-item>
                
                <el-form-item prop="password">
                  <el-input
                    v-model="registerForm.password"
                    type="password"
                    placeholder="密码"
                    :prefix-icon="Lock"
                    show-password
                    class="premium-input"
                  />
                </el-form-item>
                
                <el-form-item prop="confirmPassword">
                  <el-input
                    v-model="registerForm.confirmPassword"
                    type="password"
                    placeholder="确认密码"
                    :prefix-icon="Lock"
                    show-password
                    class="premium-input"
                    @keyup.enter="handleRegister"
                  />
                </el-form-item>
                
                <el-button
                  type="primary"
                  class="submit-btn"
                  @click="handleRegister"
                  :loading="loading"
                >
                  立即注册
                </el-button>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Lock, Message, Monitor, Connection, UserFilled } from '@element-plus/icons-vue'
import { ElMessage, FormInstance, FormRules } from 'element-plus'
import { authApi } from '@/services/api/auth'

const router = useRouter()
const route = useRoute()

const activeTab = ref('login')
const loading = ref(false)
const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()

const loginForm = reactive({
  username: '',
  password: '',
  remember: false
})

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const loginRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ]
}

const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名长度不能少于3位', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const response = await authApi.login({
        username: loginForm.username,
        password: loginForm.password
      })
      
      // 如果请求成功（没有抛出异常），说明登录成功
      if (response.token) {
        localStorage.setItem('token', response.token)
        localStorage.setItem('userId', response.userId?.toString() || '')
        ElMessage.success(response.message || '登录成功')

        const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/chat'
        const safeRedirect = redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/chat'
        router.push(safeRedirect)
      } else {
        ElMessage.error(response.message || '登录失败')
      }
    } catch (error: any) {
      // 错误已经在request.ts的拦截器中处理，这里只显示具体错误信息
      const errorMessage = error.response?.data?.message || error.message || '登录失败'
      ElMessage.error(errorMessage)
    } finally {
      loading.value = false
    }
  })
}

const handleRegister = async () => {
  if (!registerFormRef.value) return
  
  await registerFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const response = await authApi.register({
        username: registerForm.username,
        email: registerForm.email,
        password: registerForm.password
      })
      
      // 如果请求成功（没有抛出异常），说明注册成功
      if (response.token || response.message) {
        ElMessage.success(response.message || '注册成功，请登录')
        activeTab.value = 'login'
        loginForm.username = registerForm.username
      } else {
        ElMessage.error(response.message || '注册失败')
      }
    } catch (error: any) {
      // 错误已经在request.ts的拦截器中处理，这里只显示具体错误信息
      const errorMessage = error.response?.data?.message || error.message || '注册失败'
      ElMessage.error(errorMessage)
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped lang="scss">
.login-view {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background-color: var(--bg-app);
}

/* Ambient Background */
.ambient-glow {
  position: absolute;
  width: 800px;
  height: 800px;
  border-radius: 50%;
  filter: blur(120px);
  opacity: 0.3;
  z-index: 0;
  pointer-events: none;
}
.top-left {
  top: -300px;
  left: -200px;
  background: radial-gradient(circle, var(--primary-color) 0%, transparent 70%);
}
.bottom-right {
  bottom: -300px;
  right: -200px;
  background: radial-gradient(circle, #818cf8 0%, transparent 70%);
}

.login-container {
  width: 90%;
  max-width: 1000px;
  min-width: 320px;
  height: 640px;
  max-height: 90vh;
  display: flex;
  overflow: hidden;
  z-index: 10;
  border-radius: 32px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.8);
  margin: 20px;
}

/* Promo Side */
.promo-side {
  flex: 1.1;
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.05) 0%, rgba(129, 140, 248, 0.05) 100%);
  padding: 40px 60px;
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 60px;
}

.logo-box {
  width: 40px;
  height: 40px;
  background: var(--primary-color);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 20px;
  border-radius: 12px;
  font-family: var(--font-serif);
}

.brand-name {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}

.hero-text {
  margin-bottom: 40px;
}

.title {
  font-size: clamp(32px, 4vw, 44px);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  margin-bottom: 16px;
  letter-spacing: -1px;
}

.subtitle {
  font-size: clamp(14px, 2vw, 18px);
  color: var(--text-secondary);
  line-height: 1.6;
}

.visual-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.dh-aura {
  position: relative;
  width: 160px;
  height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dh-icon {
  font-size: 64px;
  color: var(--primary-color);
  z-index: 2;
}

.aura-ring {
  position: absolute;
  border: 1px solid var(--primary-fade);
  border-radius: 50%;
  animation: aura-pulse 3s infinite ease-in-out;
}

.ring-1 { width: 100%; height: 100%; animation-delay: 0s; }
.ring-2 { width: 140%; height: 140%; animation-delay: 1.5s; opacity: 0.5; }

.badges {
  display: flex;
  gap: 24px;
  margin-top: auto;
}

.badge-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.badge-item .el-icon {
  font-size: 18px;
  color: var(--primary-color);
}

/* Auth Side */
.auth-side {
  flex: 0.9;
  background: white;
  padding: 40px 60px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.auth-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.premium-tabs :deep(.el-tabs__header) {
  margin-bottom: 40px;
  border-bottom: none;
}

.premium-tabs :deep(.el-tabs__nav) {
  float: none;
  display: flex;
  justify-content: flex-start;
  gap: 32px;
}

.premium-tabs :deep(.el-tabs__item) {
  padding: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-disabled);
  height: auto;
  line-height: 1.5;
  transition: all 0.3s;
}

.premium-tabs :deep(.el-tabs__item.is-active) {
  color: var(--text-primary);
}

.premium-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--primary-color);
  height: 3px;
  border-radius: 3px;
}

.auth-header {
  margin-bottom: 32px;
}

.auth-header h2 {
  font-size: clamp(24px, 3vw, 28px);
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.auth-header p {
  color: var(--text-secondary);
  font-size: clamp(13px, 1.5vw, 15px);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.premium-input :deep(.el-input__wrapper) {
  height: 52px;
  background-color: #f8fafc !important;
  border-radius: 14px !important;
  padding-left: 16px;
}

.premium-input :deep(.el-input__inner) {
  font-weight: 500;
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 4px 0;
}

.forgot-link {
  font-size: 14px;
  color: var(--primary-color);
  font-weight: 500;
}

.submit-btn {
  height: 54px;
  border-radius: 16px;
  font-size: 16px;
  font-weight: 700;
  margin-top: 12px;
  background: var(--primary-color);
  border: none;
  box-shadow: 0 10px 20px -5px rgba(79, 70, 229, 0.4);
}

.submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 15px 30px -5px rgba(79, 70, 229, 0.5);
}

@keyframes aura-pulse {
  0% { transform: scale(1); opacity: 0.2; }
  50% { transform: scale(1.1); opacity: 0.5; }
  100% { transform: scale(1); opacity: 0.2; }
}

@media (max-width: 1200px) {
  .login-container {
    width: 95%;
    max-width: 900px;
    height: auto;
    min-height: 580px;
  }
  
  .promo-side {
    padding: 30px 40px;
  }
  
  .auth-side {
    padding: 30px 40px;
  }
}

@media (max-width: 1024px) {
  .login-container {
    width: 90%;
    height: auto;
    min-height: 600px;
  }
  .promo-side { display: none; }
  .auth-side { 
    flex: 1; 
    padding: 40px;
  }
}

@media (max-width: 768px) {
  .login-container {
    width: 95%;
    margin: 10px;
    height: auto;
    min-height: 500px;
  }
  
  .auth-side {
    padding: 30px 20px;
  }
  
  .auth-header h2 {
    font-size: 22px;
  }
  
  .auth-header p {
    font-size: 14px;
  }
  
  .premium-tabs :deep(.el-tabs__nav) {
    gap: 20px;
  }
  
  .premium-tabs :deep(.el-tabs__item) {
    font-size: 14px;
  }
}

@media (max-width: 480px) {
  .login-container {
    width: 100%;
    margin: 0;
    border-radius: 0;
    height: 100vh;
    max-height: 100vh;
  }
  
  .auth-side {
    padding: 20px;
  }
  
  .auth-header {
    margin-bottom: 20px;
  }
  
  .auth-form {
    gap: 15px;
  }
  
  .premium-input :deep(.el-input__wrapper) {
    height: 48px;
    border-radius: 12px !important;
  }
  
  .submit-btn {
    height: 50px;
    border-radius: 14px;
    font-size: 15px;
  }
}
</style>
