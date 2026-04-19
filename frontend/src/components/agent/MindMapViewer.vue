<template>
  <section class="card mindmap-card">
    <header class="card-head">
      <div class="head-left">
        <span class="head-icon">🧠</span>
        <h4>{{ titleText }}</h4>
      </div>
    </header>

    <div v-if="!sourceMarkdown" class="empty">
      <span>暂无可渲染的思维导图数据</span>
    </div>

    <div v-else class="mindmap-wrap">
      <svg ref="svgRef" class="mindmap-canvas" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'

interface CreativeTreeNode {
  id: string
  label: string
  description?: string
  children?: CreativeTreeNode[]
}

const props = defineProps<{
  title?: string
  creativeTree?: CreativeTreeNode
  outlineMarkdown?: string
}>()

const svgRef = ref<SVGSVGElement | null>(null)
const transformer = new Transformer()
let markmap: Markmap | null = null

const titleText = computed(() => props.title || '思维导图')

const treeToMarkdown = (node?: CreativeTreeNode, depth = 0): string[] => {
  if (!node) return []
  const indent = '  '.repeat(depth)
  const suffix = node.description ? ` - ${node.description}` : ''
  const lines = [`${indent}- ${node.label}${suffix}`]
  const children = Array.isArray(node.children) ? node.children : []
  for (const child of children) {
    lines.push(...treeToMarkdown(child, depth + 1))
  }
  return lines
}

const sourceMarkdown = computed(() => {
  const fromOutline = (props.outlineMarkdown || '').trim()
  if (fromOutline) return fromOutline

  if (props.creativeTree) {
    return [`# ${props.creativeTree.label}`, ...treeToMarkdown(props.creativeTree, 0)].join('\n')
  }
  return ''
})

const renderMindMap = async () => {
  await nextTick()
  const markdown = sourceMarkdown.value
  if (!svgRef.value || !markdown) return

  const { root } = transformer.transform(markdown)
  if (!markmap) {
    markmap = Markmap.create(svgRef.value)
  }
  markmap.setData(root)
  markmap.fit()
}

watch(sourceMarkdown, () => {
  renderMindMap()
})

onMounted(() => {
  renderMindMap()
})

onBeforeUnmount(() => {
  if (markmap) {
    markmap.destroy()
    markmap = null
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
  background: linear-gradient(135deg, #fffbeb, #fef3c7);
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

.empty {
  padding: 20px 12px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.mindmap-wrap {
  width: 100%;
  min-height: 300px;
  height: 360px;
  overflow: auto;
}

.mindmap-canvas {
  width: 100%;
  height: 100%;
  min-width: 640px;
}
</style>
