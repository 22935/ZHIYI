<!-- 图表查看器 — 封装 MermaidRenderer，支持全屏查看、PNG 下载和可折叠源码切换 -->
<template>
  <section class="card diagram-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Share /></el-icon>
        <h4>{{ headerTitle }}</h4>
      </div>
      <div class="head-right">
        <span v-if="diagramType" class="meta">{{ diagramType }}</span>
        <div class="head-actions">
          <button v-if="mermaidCode" class="action-btn" @click="openFullscreen" title="全屏查看">
            <el-icon><FullScreen /></el-icon>
          </button>
          <button v-if="mermaidCode" class="action-btn" @click="downloadDiagram" title="下载图片">
            <el-icon><Download /></el-icon>
          </button>
        </div>
      </div>
    </header>

    <div v-if="!mermaidCode" class="empty">
      <span>No diagram data available.</span>
    </div>

    <div v-else class="diagram-content" @click="openFullscreen" style="cursor: zoom-in;">
      <MermaidRenderer :code="mermaidCode" ref="mermaidRendererRef" />
      <details class="source-toggle" @click.stop>
        <summary>Mermaid Source</summary>
        <pre>{{ mermaidCode }}</pre>
      </details>
    </div>

    <ImageViewer
      v-model:visible="viewerVisible"
      :file-name="headerTitle + '.png'"
    >
      <div class="fullscreen-diagram" v-html="fullscreenSvg" />
    </ImageViewer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Download, FullScreen, Share } from '@element-plus/icons-vue'
import MermaidRenderer from './MermaidRenderer.vue'
import ImageViewer from '@/components/common/ImageViewer.vue'
import mermaid from 'mermaid'

interface DiagramGenerationData {
  title?: string
  diagram_type?: string
  mermaid_code?: string
}

const props = defineProps<{
  data?: DiagramGenerationData
}>()

const mermaidRendererRef = ref<InstanceType<typeof MermaidRenderer> | null>(null)
const viewerVisible = ref(false)
const fullscreenSvg = ref('')

const headerTitle = computed(() => (props.data?.title || '').trim() || 'Mermaid Diagram')
const diagramType = computed(() => (props.data?.diagram_type || '').trim())
const mermaidCode = computed(() => (props.data?.mermaid_code || '').trim())

const openFullscreen = async () => {
  if (!mermaidCode.value) return
  try {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      theme: 'default'
    })
    const renderId = `mermaid-fullscreen-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const { svg } = await mermaid.render(renderId, mermaidCode.value)
    fullscreenSvg.value = svg
    viewerVisible.value = true
  } catch {
    const rendererEl = mermaidRendererRef.value?.$el as HTMLElement
    if (rendererEl) {
      const svgEl = rendererEl.querySelector('svg') || rendererEl.querySelector('.rendered-svg')
      if (svgEl) {
        fullscreenSvg.value = svgEl.outerHTML
        viewerVisible.value = true
      }
    }
  }
}

const downloadDiagram = async () => {
  const rendererEl = mermaidRendererRef.value?.$el as HTMLElement
  if (!rendererEl) return

  const svgEl = rendererEl.querySelector('.rendered-svg svg') || rendererEl.querySelector('svg')
  if (!svgEl) return

  try {
    const svgClone = svgEl.cloneNode(true) as SVGElement
    const bbox = svgEl.getBoundingClientRect()
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
    link.download = headerTitle.value + '.png'
    link.click()
  } catch {
    const serializer = new XMLSerializer()
    const svgString = serializer.serializeToString(svgEl)
    const blob = new Blob([svgString], { type: 'image/svg+xml' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = headerTitle.value + '.svg'
    link.click()
    URL.revokeObjectURL(link.href)
  }
}
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
  background: linear-gradient(135deg, var(--accent-fade), var(--accent-fade));
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
  color: var(--primary-color);
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
  color: var(--primary-color);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: rgba(0, 0, 0, 0.08);
  color: #3730a3;
  transform: translateY(-1px);
}

.empty {
  padding: 20px 12px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.diagram-content {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: background 0.2s ease;
}

.diagram-content:hover {
  background: rgba(99, 102, 241, 0.02);
}

.source-toggle {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: var(--bg-input);
  padding: 8px 10px;
  font-size: 12px;
}

.source-toggle summary {
  cursor: pointer;
  color: var(--text-regular);
  font-weight: 600;
}

.source-toggle pre {
  margin: 8px 0 0;
  max-height: 220px;
  overflow: auto;
  padding: 8px;
  border-radius: 6px;
  background: #0f172a;
  color: #e2e8f0;
}

.fullscreen-diagram {
  background: var(--surface-solid);
  border-radius: 8px;
  padding: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: min(90vw, 1400px);
  height: min(85vh, 960px);
  min-width: 320px;
  min-height: 240px;
  overflow: hidden;
}

.fullscreen-diagram :deep(svg) {
  width: 100% !important;
  height: 100% !important;
  max-width: 100%;
  max-height: 100%;
}
</style>
