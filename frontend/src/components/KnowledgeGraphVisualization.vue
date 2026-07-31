<!-- 知识图谱可视化面板 — 含统计信息、刷新/适配视图和加载/错误/空状态的丰富知识图谱 -->
<template>
  <div class="knowledge-graph-viz">
    <div class="graph-header">
      <div class="header-left">
        <h3>知识图谱可视化</h3>
        <div class="stats">
          <span class="stat-item">实体: {{ stats.entities_count || 0 }}</span>
          <span class="stat-item">关系: {{ stats.relations_count || 0 }}</span>
          <span class="stat-item">三元组: {{ stats.triples_count || 0 }}</span>
          <span v-if="currentRoleId" class="stat-item role-badge">
            角色: {{ roleStore.currentRole?.name || '当前角色' }}
          </span>
        </div>
      </div>
      <div class="header-actions">
        <el-button @click="refreshGraph" :loading="loading" size="small">
          <el-icon><Refresh /></el-icon>
          <span>刷新</span>
        </el-button>
        <el-button @click="fitView" size="small">
          <el-icon><FullScreen /></el-icon>
          <span>适应画布</span>
        </el-button>
      </div>
    </div>
    
    <div class="graph-container" ref="graphContainerRef">
      <div v-if="loading" class="loading-overlay">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载知识图谱...</span>
      </div>
      <div v-else-if="error" class="error-overlay">
        <el-alert :title="error" type="error" :closable="false" />
      </div>
      <div v-else-if="isEmptyGraph" class="empty-overlay">
        <el-empty :description="emptyDescription">
          <template #image>
            <div class="empty-icon">KG</div>
          </template>
        </el-empty>
      </div>
      <div v-else class="graph-canvas" ref="graphCanvasRef"></div>
    </div>
    
    <div class="graph-controls">
      <div class="control-group">
        <label>布局算法:</label>
        <el-select v-model="layout" size="small" @change="applyLayout">
          <el-option label="力导向布局" value="hierarchical" />
          <el-option label="圆形布局" value="circular" />
          <el-option label="网格布局" value="grid" />
        </el-select>
      </div>
      <div class="control-group">
        <label>实体搜索:</label>
        <el-input
          v-model="entitySearch"
          placeholder="搜索实体..."
          size="small"
          @keyup.enter="searchEntity"
        >
          <template #append>
            <el-button @click="searchEntity" size="small">搜索</el-button>
          </template>
        </el-input>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import { Loading, Refresh, FullScreen } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { knowledgeGraphApi } from '@/services/api/knowledgeGraph'
import { useRoleStore } from '@/stores/role'
import { resolveKnowledgeRoleId } from '@/utils/knowledgeRole'

const graphContainerRef = ref<HTMLElement>()
const graphCanvasRef = ref<HTMLElement>()
const loading = ref(false)
const initialized = ref(false)
const error = ref<string>('')
const stats = ref<Record<string, any>>({})
const entitySearch = ref('')
const layout = ref('hierarchical')

const roleStore = useRoleStore()
const currentRoleId = computed(() => resolveKnowledgeRoleId(roleStore.currentRole))
const isEmptyGraph = computed(() => initialized.value && !loading.value && !error.value && nodes.length === 0)
const emptyDescription = computed(() => {
  if (currentRoleId.value) {
    const roleName = roleStore.currentRole?.name || '当前角色'
    return `${roleName} 暂无知识图谱数据。内置图谱仅包含律师、教师、程序员、作家角色；如果你使用的是自定义角色，需要先上传该角色的知识文档。`
  }

  return '当前还没有可展示的知识图谱数据。请先上传文档，或切换到律师、教师、程序员、作家等已内置知识的角色。'
})

let network: Network | null = null
let nodes = new DataSet<any>([])
let edges = new DataSet<any>([])
let themeObserver: MutationObserver | null = null

const cssColor = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

onMounted(async () => {
  await refreshGraph()
  themeObserver = new MutationObserver(() => renderGraph())
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-color-scheme'] })
})

onUnmounted(() => {
  themeObserver?.disconnect()
  themeObserver = null
  if (network) {
    network.destroy()
    network = null
  }
})

// 监听角色变化，重新加载图谱
watch(() => currentRoleId.value, async () => {
  if (currentRoleId.value) {
    await refreshGraph()
  }
})

/**
 * 刷新知识图谱
 */
const refreshGraph = async () => {
  try {
    loading.value = true
    error.value = ''
    
    // 获取统计信息
    const statsData = await knowledgeGraphApi.getGraphStats()
    stats.value = statsData
    
    // 获取知识图谱数据（这里需要从后端获取实体和关系数据）
    // 由于后端API可能不直接返回图谱数据，我们需要构建
    await buildGraphData()
    
    await nextTick()
    renderGraph()
  } catch (e: any) {
    error.value = '加载知识图谱失败: ' + (e.message || '未知错误')
    ElMessage.error(error.value)
  } finally {
    loading.value = false
    initialized.value = true
  }
}

/**
 * 构建图谱数据
 */
const buildGraphData = async () => {
  try {
    // 从后端获取完整的图谱数据（只获取当前角色的）
    const graphData = await knowledgeGraphApi.getGraphData(currentRoleId.value)
    
    // 检查响应是否有效
    if (!graphData) {
      console.warn('知识图谱数据为空')
      nodes.clear()
      edges.clear()
      stats.value = {
        entities_count: 0,
        triples_count: 0,
        relations_count: 0
      }
      return
    }
    
    // 更新统计信息
    stats.value = graphData.stats || {
      entities_count: graphData.nodes?.length || 0,
      triples_count: graphData.edges?.length || 0,
      relations_count: 0
    }
    
    // 构建节点数据
    const nodeData = (graphData.nodes || []).map(node => ({
      id: node.id,
      label: node.label || node.id,
      title: `${node.label || node.id}\n类型: ${node.type || 'unknown'}`,
      group: node.type || 'unknown',
      shape: 'dot',
      size: 20
    }))
    
    // 构建边数据
    const edgeData = (graphData.edges || []).map(edge => ({
      from: edge.from,
      to: edge.to,
      label: edge.label || '',
      arrows: edge.arrows || 'to',
      smooth: {
        type: 'continuous',
        roundness: 0.5
      }
    }))
    
    nodes.clear()
    edges.clear()
    
    if (nodeData.length > 0) {
      nodes.add(nodeData)
    }
    if (edgeData.length > 0) {
      edges.add(edgeData)
    }
    
    console.log('知识图谱数据构建完成:', {
      nodes: nodeData.length,
      edges: edgeData.length,
      stats: stats.value
    })
    
  } catch (e: any) {
    console.error('构建图谱数据失败:', e)
    // 如果获取失败，使用空数据
    nodes.clear()
    edges.clear()
    stats.value = {
      entities_count: 0,
      triples_count: 0,
      relations_count: 0
    }
    
    // 如果是404错误，说明知识图谱还没有构建，这是正常的
    if (e.response?.status === 404 || e.status === 404) {
      console.log('知识图谱尚未构建，这是正常的')
      error.value = '知识图谱尚未构建，请先上传文档并构建知识图谱'
    } else {
      error.value = '加载知识图谱失败: ' + (e.message || '未知错误')
    }
  }
}

/**
 * 渲染图谱
 */
const renderGraph = () => {
  if (!graphCanvasRef.value) return
  
  // 如果网络已存在，先销毁
  if (network) {
    network.destroy()
  }
  
  const primary = cssColor('--primary-color', '#6366f1')
  const primaryFade = cssColor('--primary-fade', '#eef2ff')
  const surface = cssColor('--bg-card', '#ffffff')
  const edge = cssColor('--text-disabled', '#94a3b8')
  const data = {
    nodes: nodes,
    edges: edges
  }
  
  const options: any = {
    nodes: {
      shape: 'dot',
      size: 20,
      font: {
        size: 14,
        face: 'Inter'
      },
      borderWidth: 2,
      shadow: true,
      color: {
        border: primary,
        background: surface,
        highlight: {
          border: primary,
          background: primaryFade
        }
      }
    },
    edges: {
      width: 2,
      color: {
        color: edge,
        highlight: primary
      },
      arrows: {
        to: {
          enabled: true,
          scaleFactor: 0.8
        }
      },
      font: {
        size: 12,
        align: 'middle'
      },
      smooth: {
        enabled: true,
        type: 'continuous',
        roundness: 0.5
      }
    },
    physics: {
      enabled: true,
      stabilization: {
        enabled: true,
        iterations: 200
      }
    },
    interaction: {
      hover: true,
      tooltipDelay: 200,
      zoomView: true,
      dragView: true
    },
    layout: getLayoutOptions()
  }
  
  network = new Network(graphCanvasRef.value, data, options)
  
  // 添加事件监听
  network.on('click', (params: any) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0]
      const node = nodes.get(nodeId) as any
      ElMessage.info(`选中实体: ${node?.label || nodeId}`)
    }
  })
  
  network.on('stabilized', () => {
    // 图谱稳定后可以执行的操作
  })
}

/**
 * 获取布局选项
 */
const getLayoutOptions = () => {
  switch (layout.value) {
    case 'hierarchical':
      return {
        hierarchical: {
          enabled: true,
          direction: 'UD',
          sortMethod: 'directed',
          levelSeparation: 150,
          nodeSpacing: 200
        }
      }
    case 'circular':
      return {
        randomSeed: 2
      }
    case 'grid':
      return {
        improvedLayout: true
      }
    default:
      return {}
  }
}

/**
 * 应用布局
 */
const applyLayout = () => {
  if (network) {
    network.setOptions({
      layout: getLayoutOptions()
    } as any)
    network.fit()
  }
}

/**
 * 适应画布
 */
const fitView = () => {
  if (network) {
    network.fit({
      animation: {
        duration: 500,
        easingFunction: 'easeInOutQuad'
      }
    })
  }
}

/**
 * 搜索实体
 */
const searchEntity = async () => {
  if (!entitySearch.value.trim()) {
    ElMessage.warning('请输入实体名称')
    return
  }
  
  try {
    const entityInfo = await knowledgeGraphApi.getEntityInfo(entitySearch.value)
    
    // 高亮显示相关节点
    if (network) {
      // 这里可以根据搜索结果高亮节点
      // network.selectNodes([entityInfo.id])
      network.focus(entityInfo.id, {
        scale: 1.5,
        animation: true
      })
    }
    
    ElMessage.success(`找到实体: ${entitySearch.value}`)
  } catch (e: any) {
    ElMessage.error('搜索实体失败: ' + (e.message || '未知错误'))
  }
}
</script>

<style scoped lang="scss">
.knowledge-graph-viz {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--surface-solid);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  overflow: hidden;
}

.graph-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--surface-solid);
  
  .header-left {
    display: flex;
    align-items: center;
    gap: 24px;
    
    h3 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
      color: var(--text-primary);
    }
    
    .stats {
      display: flex;
      gap: 16px;
      align-items: center;
      flex-wrap: wrap;
      
      .stat-item {
        font-size: 13px;
        color: var(--text-secondary);
        font-weight: 500;
        
        &.role-badge {
          padding: 4px 12px;
          background: rgba(99, 102, 241, 0.1);
          border-radius: 6px;
          color: var(--primary-color);
          font-weight: 600;
        }
      }
    }
  }
  
  .header-actions {
    display: flex;
    gap: 8px;
  }
}

.graph-container {
  flex: 1;
  position: relative;
  min-height: 500px;
  background: var(--bg-input);
}

.graph-canvas {
  width: 100%;
  height: 100%;
}

.loading-overlay,
.error-overlay,
.empty-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg-card) 95%, transparent);
  backdrop-filter: blur(8px);
  gap: 16px;
  z-index: 10;
}

.empty-icon {
  width: 72px;
  height: 72px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--primary-color);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(34, 211, 238, 0.18));
  border: 1px solid rgba(99, 102, 241, 0.18);
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

.graph-controls {
  padding: 16px 24px;
  border-top: 1px solid var(--border-light);
  display: flex;
  gap: 24px;
  align-items: center;
  background: var(--surface-solid);
  
  .control-group {
    display: flex;
    align-items: center;
    gap: 8px;
    
    label {
      font-size: 13px;
      color: var(--text-secondary);
      font-weight: 500;
      white-space: nowrap;
    }
  }
}
</style>

