<!-- 角色管理页面 — 展示常用角色和全部角色列表，支持选择和创建 AI 角色 -->
<template>
  <div class="role-view">
    <!-- 页面头部 -->
    <div class="page-header workspace-page-header">
      <!-- <button class="back-btn" @click="handleBack" title="返回">
        <el-icon><ArrowLeft /></el-icon>
      </button> -->
      <div class="header-inner">
        <div class="header-left">
          <div class="header-icon-wrapper workspace-page-header__icon">
            <el-icon class="header-icon"><UserFilled /></el-icon>
          </div>
          <div class="header-text">
            <h1 class="page-title">角色管理</h1>
            <p class="page-subtitle">管理和配置您的AI角色</p>
          </div>
        </div>
        <button class="create-button" @click="handleCreateRole">
          <el-icon><Plus /></el-icon>
          <span>创建角色</span>
        </button>
      </div>
    </div>

    <!-- 主要内容区域 -->
    <div class="page-content">
      <div class="content-inner">
        <!-- 常用角色 -->
        <div class="role-section" v-if="roleStore.favoriteRoles.length > 0">
          <div class="section-header">
            <h2 class="section-title">常用角色</h2>
            <span class="section-count">{{ roleStore.favoriteRoles.length }}</span>
          </div>
          <div class="role-grid">
            <RoleCard
              v-for="role in roleStore.favoriteRoles"
              :key="'fav-' + role.id"
              :role="role"
              :selected="roleStore.currentRole?.id === role.id"
              @select="handleSelectRole"
            />
          </div>
        </div>

        <!-- 内置角色 -->
        <div class="role-section">
          <div class="section-header">
            <h2 class="section-title">内置角色</h2>
            <span class="section-count">{{ roleStore.builtinRoles.length }}</span>
          </div>
          <div class="role-grid" v-loading="roleStore.loading">
            <RoleCard
              v-for="role in roleStore.builtinRoles"
              :key="role.id"
              :role="role"
              :selected="roleStore.currentRole?.id === role.id"
              @select="handleSelectRole"
            />
          </div>
        </div>

        <!-- 自定义角色 -->
        <div class="role-section">
          <div class="section-header">
            <h2 class="section-title">自定义角色</h2>
            <span class="section-count">{{ roleStore.customRoles.length }}</span>
          </div>
          <div class="role-grid" v-loading="roleStore.loading">
            <RoleCard
              v-for="role in roleStore.customRoles"
              :key="role.id"
              :role="role"
              :selected="roleStore.currentRole?.id === role.id"
              @select="handleSelectRole"
              @edit="handleEditRole"
              @delete="handleDeleteRole"
            />
            <!-- 添加角色卡片 -->
            <div class="add-role-card" @click="handleCreateRole">
              <div class="add-icon-wrapper">
                <el-icon class="add-icon"><Plus /></el-icon>
              </div>
              <div class="add-text">创建新角色</div>
              <div class="add-hint">自定义您的专属AI助手</div>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="!roleStore.loading && roleStore.builtinRoles.length === 0" class="empty-state">
          <div class="empty-icon-wrapper">
            <el-icon class="empty-icon"><UserFilled /></el-icon>
          </div>
          <h3 class="empty-title">暂无角色数据</h3>
          <p class="empty-desc">创建您的第一个AI角色开始使用</p>
        </div>
      </div>
    </div>

    <!-- 编辑角色对话框 -->
    <EditRoleDialog
      v-model="showEditDialog"
      :role="editingRole"
      @updated="handleRoleUpdated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, UserFilled } from '@element-plus/icons-vue'
import { useRoleStore } from '@/stores/role'
import RoleCard from '@/components/RoleCard.vue'
import EditRoleDialog from '@/components/EditRoleDialog.vue'
import { useChatStore } from '@/stores/chat'

const router = useRouter()
const roleStore = useRoleStore()
const chatStore = useChatStore()

const handleSelectRole = (role: any) => {
  roleStore.selectRole(role)
  chatStore.setRole(role.id)
  ElMessage.success(`已切换到角色: ${role.name}`)
}

const handleCreateRole = () => {
  // 跳转到创建角色页面
  router.push('/create-role')
}

const showEditDialog = ref(false)
const editingRole = ref<any>(null)

const handleEditRole = (role: any) => {
  editingRole.value = role
  showEditDialog.value = true
}

const handleRoleUpdated = () => {
  roleStore.loadCustomRoles()
}

const handleDeleteRole = async (role: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除角色"${role.name}"吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await roleStore.deleteRole(role.id)
    ElMessage.success('删除成功')
  } catch {
    // 用户取消
  }
}

// 监听角色创建事件
const handleRoleCreatedEvent = () => {
  roleStore.loadCustomRoles()
}

onMounted(async () => {
  await roleStore.loadBuiltinRoles()
  await roleStore.loadCustomRoles()
  
  // 监听角色创建事件（从CreateRoleView页面创建后）
  window.addEventListener('role-created', handleRoleCreatedEvent)
})

onUnmounted(() => {
  window.removeEventListener('role-created', handleRoleCreatedEvent)
})
</script>

<style scoped lang="scss">
.role-view {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
}

/* 页面头部 */
.page-header {
  flex-shrink: 0;
  background: var(--surface-solid);
  border-bottom: 1px solid var(--border-light);
  padding: var(--page-header-padding-y) var(--page-padding-x);
}

.back-btn {
  position: absolute;
  top: 32px;
  left: 24px;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: white;
  border: 1px solid var(--border-light);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  z-index: 11;

  &:hover {
    background: var(--bg-input);
    border-color: var(--primary-color);
    color: var(--primary-color);
    transform: translateX(-2px);
  }

  &:active {
    transform: scale(0.95);
  }
}

.header-inner {
  max-width: var(--page-content-max-width);
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2xl);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-xl);
}

.header-icon-wrapper {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: var(--primary-color);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.header-icon {
  font-size: 28px;
  color: #ffffff;
}

.header-text {
  .page-title {
    margin: 0 0 6px 0;
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
    line-height: 1.2;
  }
  
  .page-subtitle {
    margin: 0;
    font-size: 14px;
    color: var(--text-secondary);
    font-weight: 400;
    letter-spacing: 0.01em;
  }
}

.create-button {
  height: 40px;
  padding: 0 20px;
  background: var(--primary-color);
  border: none;
  border-radius: 10px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
  font-family: inherit;
}

.create-button:hover {
  background: var(--primary-hover);
  transform: translateY(-1px);
}

/* 主要内容区域 */
.page-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--page-padding-y) var(--page-padding-x);
}

.content-inner {
  max-width: var(--page-content-max-width);
  margin: 0 auto;
}

/* 角色区域 */
.role-section {
  margin-bottom: var(--space-3xl);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-xl);
}

.section-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  line-height: 1.2;
  position: relative;
  padding-left: 12px;
}

.section-title::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 18px;
  background: var(--primary-color);
  border-radius: 2px;
}

.section-count {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 400;
  padding: 4px 10px;
  background: var(--bg-input);
  border-radius: 12px;
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.add-role-card {
  height: 200px;
  border: 2px dashed var(--border-light);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--surface-solid);
  cursor: pointer;
  transition: all 0.2s ease;
  padding: 24px;
  text-align: center;
}

.add-role-card:hover {
  border-color: var(--primary-color);
  background: var(--primary-fade);
  transform: translateY(-2px);
}

.add-icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--primary-fade);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.add-role-card:hover .add-icon-wrapper {
  background: var(--primary-color);
}

.add-icon {
  font-size: 24px;
  color: var(--primary-color);
  transition: color 0.2s ease;
}

.add-role-card:hover .add-icon {
  color: #ffffff;
}

.add-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.add-hint {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 400;
}

/* 空状态 */
.empty-state {
  padding: var(--space-4xl) var(--space-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.empty-icon-wrapper {
  width: 80px;
  height: 80px;
  border-radius: 20px;
  background: var(--primary-fade);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
}

.empty-icon {
  font-size: 40px;
  color: var(--primary-color);
}

.empty-title {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.empty-desc {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 400;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .page-header {
    padding: var(--space-lg) var(--space-lg);
  }

  .header-inner {
    flex-direction: column;
    align-items: stretch;
    gap: var(--space-lg);
  }

  .header-left {
    gap: var(--space-md);
  }

  .header-icon-wrapper {
    width: 48px;
    height: 48px;
  }

  .header-icon {
    font-size: 24px;
  }

  .page-title {
    font-size: 24px;
  }

  .create-button {
    width: 100%;
    justify-content: center;
  }

  .page-content {
    padding: var(--space-xl) var(--space-lg);
  }

  .role-grid {
    grid-template-columns: 1fr;
  }
}
</style>

