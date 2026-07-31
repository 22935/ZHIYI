<template>
  <AcgDeliverables :deliverables="deliverables" :final-report="finalReport" />
</template>

<script setup lang="ts">
import AcgDeliverables from '@/components/agentos/AcgDeliverables.vue'
import type { AcgDeliverable } from '@/services/api/workflow'

defineProps<{ deliverables: AcgDeliverable[]; finalReport: string | null }>()
</script>
