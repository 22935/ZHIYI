<template>
  <section class="card diagram-card">
    <header class="card-head">
      <div class="head-left">
        <span class="head-icon">🧭</span>
        <h4>{{ headerTitle }}</h4>
      </div>
      <span v-if="diagramType" class="meta">{{ diagramType }}</span>
    </header>

    <div v-if="!mermaidCode" class="empty">
      <span>No diagram data available.</span>
    </div>

    <div v-else class="diagram-content">
      <MermaidRenderer :code="mermaidCode" />
      <details class="source-toggle">
        <summary>Mermaid Source</summary>
        <pre>{{ mermaidCode }}</pre>
      </details>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MermaidRenderer from './MermaidRenderer.vue'

interface DiagramGenerationData {
  title?: string
  diagram_type?: string
  mermaid_code?: string
}

const props = defineProps<{
  data?: DiagramGenerationData
}>()

const headerTitle = computed(() => (props.data?.title || '').trim() || 'Mermaid Diagram')
const diagramType = computed(() => (props.data?.diagram_type || '').trim())
const mermaidCode = computed(() => (props.data?.mermaid_code || '').trim())
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
  background: linear-gradient(135deg, #ede9fe, #e0e7ff);
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
  color: #4338ca;
  font-weight: 600;
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
}

.source-toggle {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px 10px;
  font-size: 12px;
}

.source-toggle summary {
  cursor: pointer;
  color: #475569;
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
</style>
