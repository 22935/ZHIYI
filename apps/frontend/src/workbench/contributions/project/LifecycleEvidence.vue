<template>
  <InspectorSection title="Mission / Run" :badge="lifecycle.phase">
    <p>{{ lifecycle.reason }}</p>
    <p v-if="lifecycle.isReadOnly">{{ lifecycle.unavailableReasons[0] }}</p>
    <InspectorPropertyList :rows="[
      { label: 'Selected Run', value: lifecycle.runId, code: true },
      { label: 'Current Run', value: lifecycle.currentRunId || 'NOT_OBSERVED', code: true },
      { label: 'Latest created', value: lifecycle.latestRunId || 'NOT_OBSERVED', code: true },
      { label: 'Successor', value: lifecycle.successorRunId || 'NOT_OBSERVED', code: true }
    ]" />
    <template v-if="lifecycle.failure">
      <strong>Failure evidence</strong>
      <InspectorPropertyList :rows="[
        { label: 'Layer', value: lifecycle.failure.layer },
        { label: 'Object', value: lifecycle.failure.objectId, code: true },
        { label: 'Cause', value: lifecycle.failure.reason },
        { label: 'Side effects', value: lifecycle.failure.sideEffects },
        { label: 'Checkpoint / authorization', value: lifecycle.failure.checkpoint }
      ]" />
      <p>恢复需要显式创建 successor，并由后端验证源节点、版本和能力；Checkpoint 本身不授予恢复权限。</p>
    </template>
    <template v-if="lifecycle.phase === 'COMPLETED'">
      <strong>{{ lifecycle.deliveryStatus === 'MISSING' ? 'Completed · Final deliverable missing' : 'Canonical Run deliverable' }}</strong>
      <InspectorPropertyList :rows="[
        { label: 'Artifact', value: lifecycle.deliverable?.artifactId || 'NOT_OBSERVED', code: true },
        { label: 'Content reference', value: lifecycle.deliverable?.contentRef || 'NOT_OBSERVED', code: true },
        { label: 'Provenance', value: provenance || 'NOT_OBSERVED' },
        { label: 'Download', value: lifecycle.deliverable ? '通过所选 Run 的 Artifact API 核验并下载' : '最终交付不可下载' }
      ]" />
    </template>
    <details><summary>原始状态与事实来源</summary>
      <p>Raw {{ lifecycle.rawStatus || 'NOT_OBSERVED' }} · normalized {{ lifecycle.normalizedStatus }}</p>
      <p v-for="source in lifecycle.evidenceReferences" :key="source"><code>{{ source }}</code></p>
      <p>NOT_OBSERVED: {{ lifecycle.notObserved.join(', ') }}</p>
    </details>
  </InspectorSection>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import type { LifecycleProjection } from '@/workbench/runtime/lifecycleProjection'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
const props = defineProps<{ lifecycle: LifecycleProjection; observation?: RuntimeObservation | null }>()
const provenance = computed(() => props.observation?.runId === props.lifecycle.runId
  ? props.observation.provenance.integrityStatus : null)
</script>
