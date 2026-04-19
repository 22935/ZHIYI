<template>
  <section class="mermaid-renderer">
    <div v-if="error" class="render-error">
      <div>Mermaid rendering failed, showing source code:</div>
      <pre>{{ code }}</pre>
    </div>
    <div v-else-if="svgContent" class="rendered-svg" v-html="svgContent" />
    <div v-else class="render-empty">No Mermaid code to render.</div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import mermaid from 'mermaid'

const props = defineProps<{
  code?: string
}>()

const svgContent = ref('')
const error = ref('')

const renderDiagram = async () => {
  const source = (props.code || '').trim()
  if (!source) {
    svgContent.value = ''
    error.value = ''
    return
  }

  try {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      theme: 'default'
    })
    const renderId = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const { svg } = await mermaid.render(renderId, source)
    svgContent.value = svg
    error.value = ''
  } catch (err: any) {
    svgContent.value = ''
    error.value = err?.message || 'render_error'
  }
}

watch(() => props.code, () => {
  renderDiagram()
}, { immediate: true })
</script>

<style scoped>
.mermaid-renderer {
  width: 100%;
}

.rendered-svg {
  width: 100%;
  overflow-x: auto;
  background: #fff;
}

.rendered-svg :deep(svg) {
  max-width: 100%;
  height: auto;
}

.render-empty,
.render-error {
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  padding: 12px;
  color: #475569;
  font-size: 13px;
  background: #f8fafc;
}

.render-error pre {
  margin: 8px 0 0;
  padding: 10px;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  overflow-x: auto;
}
</style>
