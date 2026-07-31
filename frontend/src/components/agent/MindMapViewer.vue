<!-- 思维导图查看器 — 使用 markmap-lib 将 Markdown 渲染为交互式思维导图 SVG，支持全屏和下载 -->
<template>
  <section class="card mindmap-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Share /></el-icon>
        <h4>{{ titleText }}</h4>
      </div>
      <div class="head-actions">
        <button v-if="sourceMarkdown" class="action-btn" @click="openFullscreen" title="全屏查看">
          <el-icon><FullScreen /></el-icon>
        </button>
        <button v-if="sourceMarkdown" class="action-btn" @click="downloadSvg" title="下载图片">
          <el-icon><Download /></el-icon>
        </button>
      </div>
    </header>

    <div v-if="!sourceMarkdown" class="empty">
      <span>暂无可渲染的思维导图数据</span>
    </div>

    <div v-else class="mindmap-wrap" @click="openFullscreen" style="cursor: zoom-in;">
      <svg ref="svgRef" class="mindmap-canvas" />
    </div>

    <ImageViewer
      v-model:visible="viewerVisible"
      :file-name="titleText + '.png'"
    >
      <div ref="fullscreenSvgContainer" class="fullscreen-mindmap" />
    </ImageViewer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Download, FullScreen, Share } from '@element-plus/icons-vue'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'
import ImageViewer from '@/components/common/ImageViewer.vue'

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
const fullscreenSvgContainer = ref<HTMLElement | null>(null)
const viewerVisible = ref(false)
const transformer = new Transformer()
let markmap: Markmap | null = null
let fullscreenMarkmap: Markmap | null = null

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

const openFullscreen = async () => {
  if (!sourceMarkdown.value) return
  viewerVisible.value = true
  await nextTick()
  await nextTick()

  if (fullscreenSvgContainer.value) {
    fullscreenSvgContainer.value.innerHTML = ''
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    svg.style.width = '90vw'
    svg.style.height = '85vh'
    svg.style.minWidth = '800px'
    fullscreenSvgContainer.value.appendChild(svg)

    if (fullscreenMarkmap) {
      fullscreenMarkmap.destroy()
      fullscreenMarkmap = null
    }

    const { root } = transformer.transform(sourceMarkdown.value)
    fullscreenMarkmap = Markmap.create(svg, { color: (markmap as any)?.options?.color })
    fullscreenMarkmap.setData(root)
    fullscreenMarkmap.fit()
  }
}

const downloadSvg = async () => {
  if (!svgRef.value) return
  try {
    const svgClone = svgRef.value.cloneNode(true) as SVGElement
    const bbox = svgRef.value.getBoundingClientRect()
    const scale = 2
    svgClone.setAttribute('width', String(bbox.width * scale))
    svgClone.setAttribute('height', String(bbox.height * scale))

    const serializer = new XMLSerializer()
    const svgString = serializer.serializeToString(svgClone)
    const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(svgBlob)

    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = reject
      img.src = url
    })

    const canvas = document.createElement('canvas')
    canvas.width = bbox.width * scale
    canvas.height = bbox.height * scale
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0)
    URL.revokeObjectURL(url)

    const link = document.createElement('a')
    link.href = canvas.toDataURL('image/png')
    link.download = titleText.value + '.png'
    link.click()
  } catch {
    const serializer = new XMLSerializer()
    const svgString = serializer.serializeToString(svgRef.value)
    const blob = new Blob([svgString], { type: 'image/svg+xml' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = titleText.value + '.svg'
    link.click()
    URL.revokeObjectURL(link.href)
  }
}

watch(sourceMarkdown, () => {
  renderMindMap()
})

watch(viewerVisible, (val) => {
  if (!val && fullscreenMarkmap) {
    fullscreenMarkmap.destroy()
    fullscreenMarkmap = null
  }
})

onMounted(() => {
  renderMindMap()
})

onBeforeUnmount(() => {
  if (markmap) {
    markmap.destroy()
    markmap = null
  }
  if (fullscreenMarkmap) {
    fullscreenMarkmap.destroy()
    fullscreenMarkmap = null
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
  color: #92400e;
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

.mindmap-wrap {
  width: 100%;
  min-height: 300px;
  height: 360px;
  overflow: auto;
  transition: background 0.2s ease;
}

.mindmap-wrap:hover {
  background: rgba(251, 191, 36, 0.03);
}

.mindmap-canvas {
  width: 100%;
  height: 100%;
  min-width: 640px;
}

.fullscreen-mindmap {
  width: 90vw;
  height: 85vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-solid);
  border-radius: 8px;
  padding: 20px;
}

.fullscreen-mindmap :deep(svg) {
  width: 100% !important;
  height: 100% !important;
}
</style>
