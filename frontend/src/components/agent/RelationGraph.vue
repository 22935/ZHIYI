<!-- 人物关系图 — 使用 vis-network 渲染人物关系网络图，支持全屏查看和图片下载 -->
<template>
  <section class="card relation-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Connection /></el-icon>
        <h4>人物关系图</h4>
      </div>
      <div class="head-right">
        <span class="meta" v-if="graphStats">{{ graphStats }}</span>
        <div class="head-actions">
          <button v-if="hasGraphData" class="action-btn" @click="openFullscreen" title="全屏查看">
            <el-icon><FullScreen /></el-icon>
          </button>
          <button v-if="hasGraphData" class="action-btn" @click="downloadGraph" title="下载图片">
            <el-icon><Download /></el-icon>
          </button>
        </div>
      </div>
    </header>

    <div v-if="!hasGraphData" class="empty">
      <span>暂无人物关系图数据</span>
    </div>

    <div v-else ref="graphRef" class="graph-canvas" @click="openFullscreen" style="cursor: zoom-in;" />

    <ImageViewer
      v-model:visible="viewerVisible"
      file-name="人物关系图.png"
    >
      <div ref="fullscreenGraphContainer" class="fullscreen-graph" />
    </ImageViewer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Connection, Download, FullScreen } from '@element-plus/icons-vue'
import { DataSet } from 'vis-data'
import { Network } from 'vis-network'
import ImageViewer from '@/components/common/ImageViewer.vue'

interface RelationGraphNode {
  id: string
  label: string
  group?: string
}

interface RelationGraphEdge {
  from: string
  to: string
  label?: string
}

interface RelationGraphData {
  nodes?: RelationGraphNode[]
  edges?: RelationGraphEdge[]
}

const props = defineProps<{
  data?: {
    relation_graph?: RelationGraphData
    relationGraph?: RelationGraphData
  }
}>()

const graphRef = ref<HTMLElement | null>(null)
const fullscreenGraphContainer = ref<HTMLElement | null>(null)
const viewerVisible = ref(false)
let network: Network | null = null
let fullscreenNetwork: Network | null = null

const relationGraph = computed(() => props.data?.relation_graph || props.data?.relationGraph)
const hasGraphData = computed(() => {
  const nodes = relationGraph.value?.nodes
  return Array.isArray(nodes) && nodes.length > 0
})

const graphStats = computed(() => {
  if (!hasGraphData.value) return ''
  const nodes = relationGraph.value?.nodes || []
  const edges = relationGraph.value?.edges || []
  return `${nodes.length} 节点 / ${edges.length} 关系`
})

const getNetworkOptions = () => ({
  autoResize: true,
  physics: {
    stabilization: true
  },
  interaction: {
    hover: true,
    dragNodes: true
  },
  nodes: {
    font: {
      size: 14
    },
    borderWidth: 1.5
  },
  edges: {
    font: {
      size: 12,
      align: 'middle'
    },
    color: {
      color: '#94a3b8',
      highlight: '#d97706'
    }
  },
  groups: {
    character: { color: { background: '#fde68a', border: '#d97706' } },
    protagonist: { color: { background: '#93c5fd', border: '#2563eb' } },
    antagonist: { color: { background: '#fca5a5', border: '#dc2626' } }
  }
})

const renderGraph = async () => {
  await nextTick()
  if (!graphRef.value || !hasGraphData.value) return

  const nodeRows = (relationGraph.value?.nodes || []).map(node => ({
    id: node.id,
    label: node.label || node.id,
    group: node.group || 'character',
    shape: 'dot',
    size: 18
  }))
  const edgeRows = (relationGraph.value?.edges || []).map((edge, index) => ({
    id: `e-${index}`,
    from: edge.from,
    to: edge.to,
    label: edge.label || '',
    arrows: 'to',
    smooth: { enabled: true, type: 'dynamic' }
  }))

  if (network) {
    network.destroy()
    network = null
  }

  const data = {
    nodes: new DataSet(nodeRows),
    edges: new DataSet(edgeRows)
  }
  network = new Network(graphRef.value, data as any, getNetworkOptions() as any)
}

const openFullscreen = async () => {
  if (!hasGraphData.value) return
  viewerVisible.value = true
  await nextTick()
  await nextTick()

  if (fullscreenGraphContainer.value) {
    fullscreenGraphContainer.value.innerHTML = ''

    const nodeRows = (relationGraph.value?.nodes || []).map(node => ({
      id: node.id,
      label: node.label || node.id,
      group: node.group || 'character',
      shape: 'dot',
      size: 24
    }))
    const edgeRows = (relationGraph.value?.edges || []).map((edge, index) => ({
      id: `e-fs-${index}`,
      from: edge.from,
      to: edge.to,
      label: edge.label || '',
      arrows: 'to',
      smooth: { enabled: true, type: 'dynamic' }
    }))

    if (fullscreenNetwork) {
      fullscreenNetwork.destroy()
      fullscreenNetwork = null
    }

    const data = {
      nodes: new DataSet(nodeRows),
      edges: new DataSet(edgeRows)
    }
    const options = {
      ...getNetworkOptions(),
      nodes: {
        font: { size: 18 },
        borderWidth: 2
      },
      edges: {
        font: { size: 14, align: 'middle' },
        color: {
          color: '#94a3b8',
          highlight: '#d97706'
        }
      }
    }
    fullscreenNetwork = new Network(fullscreenGraphContainer.value, data as any, options as any)
  }
}

const downloadGraph = async () => {
  if (!graphRef.value) return
  try {
    const canvasEl = graphRef.value.querySelector('canvas') as HTMLCanvasElement
    if (canvasEl) {
      const dataUrl = canvasEl.toDataURL('image/png')
      const link = document.createElement('a')
      link.href = dataUrl
      link.download = '人物关系图.png'
      link.click()
    }
  } catch {
    const canvasEl = graphRef.value.querySelector('canvas') as HTMLCanvasElement
    if (canvasEl) {
      const link = document.createElement('a')
      link.href = canvasEl.toDataURL('image/png')
      link.download = '人物关系图.png'
      link.click()
    }
  }
}

watch(relationGraph, () => {
  renderGraph()
}, { deep: true })

watch(viewerVisible, (val) => {
  if (!val && fullscreenNetwork) {
    fullscreenNetwork.destroy()
    fullscreenNetwork = null
  }
})

onMounted(() => {
  renderGraph()
})

onBeforeUnmount(() => {
  if (network) {
    network.destroy()
    network = null
  }
  if (fullscreenNetwork) {
    fullscreenNetwork.destroy()
    fullscreenNetwork = null
  }
})
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-solid);
  overflow: hidden;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
}

.head-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.head-icon {
  font-size: 14px;
}

.card-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.head-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.meta {
  font-size: 11px;
  color: #9a3412;
  font-weight: 600;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: rgba(0, 0, 0, 0.04);
  color: #9a3412;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: rgba(0, 0, 0, 0.08);
  color: #78350f;
  transform: translateY(-1px);
}

.empty {
  padding: 20px 12px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.graph-canvas {
  width: 100%;
  height: 360px;
  min-height: 280px;
  transition: background 0.2s ease;
}

.graph-canvas:hover {
  background: rgba(217, 119, 6, 0.02);
}

.fullscreen-graph {
  width: 90vw;
  height: 85vh;
  background: var(--surface-solid);
  border-radius: 8px;
  padding: 20px;
}
</style>
