<!-- 信息导航中枢页面 — 以卡片形式提供知识库、角色管理、系统设置等快捷入口 -->
<template>
  <div class="info-view">
    <el-card class="info-card">
      <template #header>
        <div class="card-header">
          <h3>信息入口</h3>
        </div>
      </template>
      
      <div class="info-content">
        <el-row :gutter="20">
          <el-col :span="8">
            <el-card class="info-item" shadow="hover">
              <div class="info-icon">
                <el-icon :size="48"><Document /></el-icon>
              </div>
              <h4>知识库</h4>
              <p>管理和查询知识库内容</p>
              <el-button type="primary" @click="$router.push('/rag')">进入</el-button>
            </el-card>
          </el-col>
          
          <el-col :span="8">
            <el-card class="info-item" shadow="hover">
              <div class="info-icon">
                <el-icon :size="48"><User /></el-icon>
              </div>
              <h4>角色管理</h4>
              <p>创建和管理AI角色</p>
              <el-button type="primary" @click="$router.push('/roles')">进入</el-button>
            </el-card>
          </el-col>
          
          <el-col :span="8">
            <el-card class="info-item" shadow="hover">
              <div class="info-icon">
                <el-icon :size="48"><Setting /></el-icon>
              </div>
              <h4>系统设置</h4>
              <p>配置系统参数和偏好</p>
              <el-button type="primary" @click="$router.push('/settings')">进入</el-button>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { Document, User, Setting } from '@element-plus/icons-vue'
</script>

<style scoped lang="scss">
.info-view {
  height: 100%;
  overflow-y: auto;
  padding: var(--page-padding-y) var(--page-padding-x);
  background: var(--bg-app);
}

.info-card {
  min-height: 400px;
  border: 1px solid var(--border-color-base);
  box-shadow: var(--box-shadow-base);
}

.card-header {
  h3 {
    margin: 0;
    font-size: var(--font-size-xl);
    font-weight: 700;
    color: var(--text-color-primary);
    letter-spacing: -0.01em;
  }
}

.info-content {
  padding: var(--spacing-lg) 0;
}

.info-item {
  text-align: center;
  height: 100%;
  border: 1px solid var(--border-color-base);
  box-shadow: var(--box-shadow-base);
  transition: var(--transition-base);
  
  &:hover {
    border-color: var(--primary-color);
    box-shadow: var(--box-shadow-hover);
  }
  
  .info-icon {
    margin-bottom: var(--spacing-md);
    color: var(--primary-color);
    transition: var(--transition-base);
  }
  
  &:hover .info-icon {
    transform: scale(1.1);
  }
  
  h4 {
    margin: var(--spacing-md) 0;
    font-size: var(--font-size-md);
    font-weight: 600;
    color: var(--text-color-primary);
    letter-spacing: -0.01em;
  }
  
  p {
    margin: var(--spacing-sm) 0 var(--spacing-md);
    color: var(--text-color-secondary);
    font-size: var(--font-size-base);
    line-height: 1.6;
    letter-spacing: 0.01em;
  }
}
</style>


