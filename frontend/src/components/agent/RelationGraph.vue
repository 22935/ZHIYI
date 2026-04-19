<template>
  <section class="card relation-card">
    <header class="card-head">
      <div class="head-left">
        <span class="head-icon">🕸️</span>
        <h4>人物关系图</h4>
      </div>
      <span class="meta" v-if="graphStats">{{ graphStats }}</span>
    </header>

    <div v-if="!hasGraphData" class="empty">
      <span>暂无人物关系图数据</span>
    </div>

    <div v-else ref="graphRef" class="graph-canvas" />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { DataSet } from 'vis-data'
import { Network } from 'vis-network'

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
let network: Network | null = null

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
  const options = {
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
  }

  network = new Network(graphRef.value, data as any, options as any)
}

watch(relationGraph, () => {
  renderGraph()
}, { deep: true })

onMounted(() => {
  renderGraph()
})

onBeforeUnmount(() => {
  if (network) {
    network.destroy()
    network = null
  }
})
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(135deg, #fff7ed, #ffedd5);
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

.meta {
  font-size: 11px;
  color: #9a3412;
  font-weight: 600;
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
}
</style>
