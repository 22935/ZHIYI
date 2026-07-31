<!-- 知识图谱视图 — 展示知识图谱统计（实体、三元组、关系）和可视化画布 -->
<template>
  <div class="knowledge-graph-container">
    <div class="graph-header">
      <h3>知识图谱</h3>
      <el-button @click="refreshStats" :loading="loading">刷新统计</el-button>
    </div>

    <div class="graph-stats" v-if="stats">
      <el-card>
        <template #header>
          <span>图谱统计</span>
        </template>
        <div class="stats-content">
          <div class="stat-item">
            <span class="label">实体数量:</span>
            <span class="value">{{ stats.entities_count || 0 }}</span>
          </div>
          <div class="stat-item">
            <span class="label">三元组数量:</span>
            <span class="value">{{ stats.triples_count || 0 }}</span>
          </div>
          <div class="stat-item">
            <span class="label">关系数量:</span>
            <span class="value">{{ stats.relations_count || 0 }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <div class="graph-visualization" ref="graphContainerRef">
      <div v-if="loading" class="loading-overlay">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载知识图谱...</span>
      </div>
      <div v-else-if="error" class="error-overlay">
        <el-alert :title="error" type="error" :closable="false" />
      </div>
      <div v-else class="graph-canvas" ref="graphCanvasRef">
        <!-- 知识图谱可视化区域 -->
        <div class="graph-placeholder">
          <el-empty description="知识图谱可视化（可集成D3.js或Cytoscape.js）" />
        </div>
      </div>
    </div>

    <div class="entity-search">
      <el-input
        v-model="entitySearchQuery"
        placeholder="搜索实体..."
        @keyup.enter="searchEntity"
      >
        <template #append>
          <el-button @click="searchEntity">搜索</el-button>
        </template>
      </el-input>
      <div v-if="entityInfo" class="entity-info">
        <el-card>
          <template #header>
            <span>实体信息: {{ entitySearchQuery }}</span>
          </template>
          <pre>{{ JSON.stringify(entityInfo, null, 2) }}</pre>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { knowledgeGraphApi } from '@/services/api/knowledgeGraph'

const graphContainerRef = ref<HTMLElement>()
const graphCanvasRef = ref<HTMLElement>()
const loading = ref(false)
const error = ref<string>('')
const stats = ref<Record<string, any> | null>(null)
const entitySearchQuery = ref('')
const entityInfo = ref<Record<string, any> | null>(null)

onMounted(async () => {
  await refreshStats()
})

/**
 * 刷新统计信息
 */
const refreshStats = async () => {
  try {
    loading.value = true
    error.value = ''
    const result = await knowledgeGraphApi.getGraphStats()
    stats.value = result
  } catch (e: any) {
    error.value = '获取统计信息失败: ' + e.message
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

/**
 * 搜索实体
 */
const searchEntity = async () => {
  if (!entitySearchQuery.value.trim()) {
    ElMessage.warning('请输入实体名称')
    return
  }

  try {
    loading.value = true
    error.value = ''
    const result = await knowledgeGraphApi.getEntityInfo(entitySearchQuery.value)
    entityInfo.value = result
  } catch (e: any) {
    error.value = '查询实体失败: ' + e.message
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
.knowledge-graph-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--spacing-lg);
  padding: var(--spacing-xl);
  background: var(--bg-color-page);
}

.graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-lg);
  background: var(--bg-color);
  border-radius: var(--border-radius-large);
  box-shadow: var(--box-shadow-base);
  border: 1px solid var(--border-color-base);
}

.graph-stats {
  flex-shrink: 0;
}

.stats-content {
  display: flex;
  gap: 32px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  
  .label {
    font-size: 14px;
    color: var(--text-secondary);
    font-weight: 500;
  }
  
  .value {
    font-size: 28px;
    font-weight: 700;
    color: var(--primary-color);
    letter-spacing: -0.02em;
  }
}

.graph-visualization {
  flex: 1;
  position: relative;
  border: 1px solid var(--border-color-base);
  border-radius: var(--border-radius-large);
  overflow: hidden;
  background: var(--bg-color);
  box-shadow: var(--box-shadow-base);
}

.graph-canvas {
  width: 100%;
  height: 100%;
  min-height: 400px;
}

.graph-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 16px;
}

.loading-overlay,
.error-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg-color-overlay);
  backdrop-filter: blur(8px);
  gap: var(--spacing-md);
  z-index: 10;
}

.is-loading {
  animation: rotate 1s linear infinite;
  color: var(--primary-color);
  font-size: 32px;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.entity-search {
  flex-shrink: 0;
  padding: var(--spacing-lg);
  background: var(--bg-color);
  border-radius: var(--border-radius-large);
  box-shadow: var(--box-shadow-base);
  border: 1px solid var(--border-color-base);
}

.entity-info {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--bg-color);
  border-radius: var(--border-radius-base);
  border: 1px solid var(--border-color-base);
  
  pre {
    max-height: 300px;
    overflow: auto;
    background: var(--surface-solid);
    padding: 16px;
    border-radius: 8px;
    border: 1px solid #e4e7ed;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-regular);
  }
}
</style>

