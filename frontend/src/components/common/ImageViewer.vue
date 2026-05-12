<template>
  <Teleport to="body">
    <Transition name="viewer-fade">
      <div
        v-if="visible"
        class="image-viewer-overlay"
        @click.self="handleOverlayClick"
        @keydown.esc="close"
      >
        <div class="viewer-backdrop" @click="close" />

        <div
          ref="containerRef"
          class="viewer-container"
          tabindex="0"
          @keydown.esc="close"
          @keydown.plus="zoomIn"
          @keydown.minus="zoomOut"
          @keydown.equal="zoomIn"
          @keydown.arrow-up="panUp"
          @keydown.arrow-down="panDown"
          @keydown.arrow-left="panLeft"
          @keydown.arrow-right="panRight"
          @keydown.digit0="resetView"
        >
          <div
            class="viewer-canvas"
            ref="canvasRef"
            @wheel.prevent="handleWheel"
            @mousedown.prevent="handleMouseDown"
            @mousemove.prevent="handleMouseMove"
            @mouseup="handleMouseUp"
            @mouseleave="handleMouseUp"
            @touchstart.passive="handleTouchStart"
            @touchmove.prevent="handleTouchMove"
            @touchend="handleTouchEnd"
            @dblclick="handleDoubleClick"
          >
            <div
              class="viewer-content"
              :style="transformStyle"
            >
              <slot>
                <img
                  v-if="src"
                  :src="src"
                  :alt="alt"
                  class="viewer-image"
                  draggable="false"
                  @load="onImageLoad"
                />
              </slot>
            </div>
          </div>

          <div class="viewer-toolbar">
            <div class="toolbar-group">
              <button class="toolbar-btn" @click="zoomOut" title="缩小 (-)">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4" />
                  <line x1="12" y1="12" x2="16.5" y2="16.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                  <line x1="5" y1="8" x2="11" y2="8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                </svg>
              </button>

              <span class="zoom-display" @click="resetView" title="重置缩放 (0)">
                {{ zoomPercent }}%
              </span>

              <button class="toolbar-btn" @click="zoomIn" title="放大 (+)">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4" />
                  <line x1="12" y1="12" x2="16.5" y2="16.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                  <line x1="5" y1="8" x2="11" y2="8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                  <line x1="8" y1="5" x2="8" y2="11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                </svg>
              </button>
            </div>

            <div class="toolbar-divider" />

            <div class="toolbar-group">
              <button class="toolbar-btn" @click="resetView" title="适应窗口 (0)">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M2 6V3a1 1 0 0 1 1-1h3M12 2h3a1 1 0 0 1 1 1v3M16 12v3a1 1 0 0 1-1 1h-3M6 16H3a1 1 0 0 1-1-1v-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>

              <button class="toolbar-btn" @click="zoomToActual" title="原始大小 (1:1)">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <rect x="2" y="2" width="14" height="14" rx="1.5" stroke="currentColor" stroke-width="1.4" />
                  <text x="9" y="12" text-anchor="middle" fill="currentColor" font-size="7" font-weight="600">1:1</text>
                </svg>
              </button>
            </div>

            <div class="toolbar-divider" />

            <div class="toolbar-group">
              <button class="toolbar-btn" @click="rotateLeft" title="向左旋转">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M4 9a5 5 0 1 1 1.5 3.6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                  <path d="M4 6v3h3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>

              <button class="toolbar-btn" @click="rotateRight" title="向右旋转">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M14 9a5 5 0 1 0-1.5 3.6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                  <path d="M14 6v3h-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>
            </div>

            <div class="toolbar-divider" />

            <div class="toolbar-group">
              <button class="toolbar-btn" @click="downloadImage" title="下载图片">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M9 2v9M5.5 8L9 11.5 12.5 8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
                  <path d="M2 13v2a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                </svg>
              </button>
            </div>
          </div>

          <button class="viewer-close" @click="close" title="关闭 (Esc)">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <line x1="5" y1="5" x2="15" y2="15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
              <line x1="15" y1="5" x2="5" y2="15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          </button>

          <div class="viewer-hint" v-if="showHint">
            <span>滚轮缩放 · 拖动平移 · 双击适应 · Esc 关闭</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  visible: boolean
  src?: string
  alt?: string
  fileName?: string
  closeOnOverlay?: boolean
}>(), {
  closeOnOverlay: true,
  alt: '',
  fileName: ''
})

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'close'): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLElement | null>(null)

const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const rotation = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const dragStartTranslateX = ref(0)
const dragStartTranslateY = ref(0)
const showHint = ref(true)

const MIN_SCALE = 0.1
const MAX_SCALE = 10
const ZOOM_STEP = 0.15
const PAN_STEP = 50

let hintTimer: ReturnType<typeof setTimeout> | null = null
let touchStartDistance = 0
let touchStartScale = 1

const zoomPercent = computed(() => Math.round(scale.value * 100))

const transformStyle = computed(() => ({
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value}) rotate(${rotation.value}deg)`,
  transition: isDragging.value ? 'none' : 'transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1)',
  transformOrigin: 'center center'
}))

const close = () => {
  emit('update:visible', false)
  emit('close')
}

const handleOverlayClick = () => {
  if (props.closeOnOverlay) close()
}

const clampScale = (value: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))

const zoomIn = () => {
  scale.value = clampScale(scale.value * (1 + ZOOM_STEP))
}

const zoomOut = () => {
  scale.value = clampScale(scale.value * (1 - ZOOM_STEP))
}

const zoomToActual = () => {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
}

const resetView = () => {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
  rotation.value = 0
}

const rotateLeft = () => {
  rotation.value -= 90
}

const rotateRight = () => {
  rotation.value += 90
}

const panUp = () => { translateY.value += PAN_STEP }
const panDown = () => { translateY.value -= PAN_STEP }
const panLeft = () => { translateX.value += PAN_STEP }
const panRight = () => { translateX.value -= PAN_STEP }

const handleWheel = (e: WheelEvent) => {
  const delta = e.deltaY > 0 ? -1 : 1
  const factor = 1 + ZOOM_STEP * delta
  const newScale = clampScale(scale.value * factor)

  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) {
    scale.value = newScale
    return
  }

  const mouseX = e.clientX - rect.left - rect.width / 2
  const mouseY = e.clientY - rect.top - rect.height / 2
  const scaleRatio = newScale / scale.value

  translateX.value = mouseX - scaleRatio * (mouseX - translateX.value)
  translateY.value = mouseY - scaleRatio * (mouseY - translateY.value)
  scale.value = newScale
}

const handleMouseDown = (e: MouseEvent) => {
  if (e.button !== 0) return
  isDragging.value = true
  dragStartX.value = e.clientX
  dragStartY.value = e.clientY
  dragStartTranslateX.value = translateX.value
  dragStartTranslateY.value = translateY.value
}

const handleMouseMove = (e: MouseEvent) => {
  if (!isDragging.value) return
  translateX.value = dragStartTranslateX.value + (e.clientX - dragStartX.value)
  translateY.value = dragStartTranslateY.value + (e.clientY - dragStartY.value)
}

const handleMouseUp = () => {
  isDragging.value = false
}

const getTouchDistance = (touches: TouchList) => {
  const dx = touches[0].clientX - touches[1].clientX
  const dy = touches[0].clientY - touches[1].clientY
  return Math.sqrt(dx * dx + dy * dy)
}

const handleTouchStart = (e: TouchEvent) => {
  if (e.touches.length === 2) {
    touchStartDistance = getTouchDistance(e.touches)
    touchStartScale = scale.value
  } else if (e.touches.length === 1) {
    isDragging.value = true
    dragStartX.value = e.touches[0].clientX
    dragStartY.value = e.touches[0].clientY
    dragStartTranslateX.value = translateX.value
    dragStartTranslateY.value = translateY.value
  }
}

const handleTouchMove = (e: TouchEvent) => {
  if (e.touches.length === 2) {
    const currentDistance = getTouchDistance(e.touches)
    const ratio = currentDistance / touchStartDistance
    scale.value = clampScale(touchStartScale * ratio)
  } else if (e.touches.length === 1 && isDragging.value) {
    translateX.value = dragStartTranslateX.value + (e.touches[0].clientX - dragStartX.value)
    translateY.value = dragStartTranslateY.value + (e.touches[0].clientY - dragStartY.value)
  }
}

const handleTouchEnd = () => {
  isDragging.value = false
}

const handleDoubleClick = () => {
  if (Math.abs(scale.value - 1) < 0.01 && translateX.value === 0 && translateY.value === 0) {
    zoomToActual()
  } else {
    resetView()
  }
}

const onImageLoad = () => {
  resetView()
}

const parseSvgLength = (value: string | null): number => {
  if (!value) return 0
  const text = value.trim()
  if (!text || text.endsWith('%')) return 0
  const numeric = Number.parseFloat(text)
  return Number.isFinite(numeric) ? numeric : 0
}

const resolveSvgRenderSize = (svgEl: SVGElement): { width: number; height: number } => {
  const rect = svgEl.getBoundingClientRect()
  let width = Math.round(rect.width)
  let height = Math.round(rect.height)

  if (width > 0 && height > 0) {
    return { width, height }
  }

  const viewBox = (svgEl.getAttribute('viewBox') || '')
    .trim()
    .split(/\s+/)
    .map(token => Number.parseFloat(token))
  if (viewBox.length === 4 && Number.isFinite(viewBox[2]) && Number.isFinite(viewBox[3])) {
    width = Math.round(Math.abs(viewBox[2]))
    height = Math.round(Math.abs(viewBox[3]))
    if (width > 0 && height > 0) {
      return { width, height }
    }
  }

  width = Math.round(parseSvgLength(svgEl.getAttribute('width')))
  height = Math.round(parseSvgLength(svgEl.getAttribute('height')))
  if (width > 0 && height > 0) {
    return { width, height }
  }

  return { width: 1024, height: 768 }
}

const downloadImage = async () => {
  try {
    let dataUrl: string | null = null

    if (canvasRef.value) {
      const content = canvasRef.value.querySelector('.viewer-content')
      if (content) {
        const svgEl = content.querySelector('svg') as SVGElement | null
        const canvasEl = content.querySelector('canvas')
        const imgEl = content.querySelector('img')

        if (svgEl) {
          const svgClone = svgEl.cloneNode(true) as SVGElement
          const renderSize = resolveSvgRenderSize(svgEl)
          const exportScale = 2
          const exportWidth = Math.max(1, Math.round(renderSize.width * exportScale))
          const exportHeight = Math.max(1, Math.round(renderSize.height * exportScale))
          svgClone.setAttribute('width', String(exportWidth))
          svgClone.setAttribute('height', String(exportHeight))
          if (!svgClone.getAttribute('viewBox')) {
            svgClone.setAttribute('viewBox', `0 0 ${Math.max(1, renderSize.width)} ${Math.max(1, renderSize.height)}`)
          }

          const serializer = new XMLSerializer()
          const svgString = serializer.serializeToString(svgClone)
          const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
          const url = URL.createObjectURL(svgBlob)

          const img = new Image()
          img.crossOrigin = 'anonymous'
          await new Promise<void>((resolve, reject) => {
            img.onload = () => resolve()
            img.onerror = reject
            img.src = url
          })

          const c = document.createElement('canvas')
          c.width = exportWidth
          c.height = exportHeight
          const ctx = c.getContext('2d')!
          ctx.fillStyle = '#ffffff'
          ctx.fillRect(0, 0, exportWidth, exportHeight)
          ctx.drawImage(img, 0, 0, exportWidth, exportHeight)
          dataUrl = c.toDataURL('image/png')
          URL.revokeObjectURL(url)
        } else if (canvasEl) {
          dataUrl = canvasEl.toDataURL('image/png')
        } else if (imgEl) {
          if (props.src && !props.src.startsWith('data:')) {
            const response = await fetch(props.src)
            const blob = await response.blob()
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = props.fileName || 'image.png'
            link.click()
            URL.revokeObjectURL(url)
            return
          }
          const c = document.createElement('canvas')
          const img = imgEl as HTMLImageElement
          c.width = img.naturalWidth || img.width
          c.height = img.naturalHeight || img.height
          const ctx = c.getContext('2d')!
          ctx.drawImage(img, 0, 0)
          dataUrl = c.toDataURL('image/png')
        }
      }
    }

    if (dataUrl) {
      const link = document.createElement('a')
      link.href = dataUrl
      link.download = props.fileName || 'image.png'
      link.click()
    }
  } catch {
    if (props.src) {
      const link = document.createElement('a')
      link.href = props.src
      link.download = props.fileName || 'image.png'
      link.target = '_blank'
      link.click()
    }
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    nextTick(() => {
      containerRef.value?.focus()
      resetView()
    })
    showHint.value = true
    if (hintTimer) clearTimeout(hintTimer)
    hintTimer = setTimeout(() => {
      showHint.value = false
    }, 3000)
  }
  toggleBodyScroll(val)
})

const toggleBodyScroll = (lock: boolean) => {
  document.body.style.overflow = lock ? 'hidden' : ''
}

onMounted(() => {
  if (props.visible) toggleBodyScroll(true)
})

onUnmounted(() => {
  toggleBodyScroll(false)
  if (hintTimer) clearTimeout(hintTimer)
})
</script>

<style scoped>
.image-viewer-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.viewer-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(8px);
}

.viewer-container {
  position: relative;
  width: 100%;
  height: 100%;
  outline: none;
}

.viewer-canvas {
  position: absolute;
  inset: 0;
  overflow: hidden;
  cursor: grab;
  display: flex;
  align-items: center;
  justify-content: center;
}

.viewer-canvas:active {
  cursor: grabbing;
}

.viewer-content {
  display: inline-flex;
  will-change: transform;
}

.viewer-image {
  max-width: 90vw;
  max-height: 85vh;
  object-fit: contain;
  user-select: none;
  -webkit-user-drag: none;
}

.viewer-toolbar {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: rgba(15, 23, 42, 0.75);
  backdrop-filter: blur(16px);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  z-index: 10;
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: rgba(255, 255, 255, 0.15);
  margin: 0 4px;
}

.toolbar-btn {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toolbar-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}

.toolbar-btn:active {
  transform: scale(0.92);
}

.zoom-display {
  min-width: 52px;
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
  transition: background 0.2s;
  user-select: none;
}

.zoom-display:hover {
  background: rgba(255, 255, 255, 0.1);
}

.viewer-close {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(12px);
  color: rgba(255, 255, 255, 0.8);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  z-index: 10;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.viewer-close:hover {
  background: rgba(239, 68, 68, 0.7);
  color: #fff;
  transform: scale(1.05);
}

.viewer-hint {
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(12px);
  border-radius: 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  white-space: nowrap;
  pointer-events: none;
  animation: hint-fade 3s ease forwards;
}

@keyframes hint-fade {
  0%, 70% { opacity: 1; }
  100% { opacity: 0; }
}

.viewer-fade-enter-active {
  transition: opacity 0.25s ease;
}

.viewer-fade-leave-active {
  transition: opacity 0.2s ease;
}

.viewer-fade-enter-from,
.viewer-fade-leave-to {
  opacity: 0;
}

@media (max-width: 640px) {
  .viewer-toolbar {
    bottom: 16px;
    padding: 4px 8px;
    border-radius: 10px;
    gap: 2px;
  }

  .toolbar-btn {
    width: 30px;
    height: 30px;
  }

  .toolbar-divider {
    margin: 0 2px;
  }

  .zoom-display {
    min-width: 44px;
    font-size: 11px;
  }

  .viewer-close {
    top: 12px;
    right: 12px;
    width: 36px;
    height: 36px;
  }

  .viewer-hint {
    bottom: 68px;
    font-size: 11px;
  }
}
</style>
