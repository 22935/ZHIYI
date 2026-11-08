<template>
  <section class="artifact-verification" aria-label="产物验证" :class="{ 'is-warning': verification?.status !== 'passed' }">
    <strong>产物验证：{{ statusLabel }}</strong>
    <p>执行状态表示任务是否结束；以下是产物自带的验证声明，不等同于独立测试结果。</p>
    <template v-if="verification">
      <InspectorDetails v-if="verification.checks.length" title="验证检查" :count="verification.checks.length">
        <ol>
          <li v-for="(check, index) in verification.checks" :key="index">
            <strong>{{ check.criterion || '未提供检查标准' }}</strong>
            <p>结果：{{ check.result || '未提供' }}</p>
            <p v-if="check.evidence">依据：{{ check.evidence }}</p>
          </li>
        </ol>
      </InspectorDetails>
      <InspectorDetails v-if="verification.unresolvedGaps.length" title="未解决缺口" :count="verification.unresolvedGaps.length">
        <ul><li v-for="(gap, index) in verification.unresolvedGaps" :key="index">{{ gap }}</li></ul>
      </InspectorDetails>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import InspectorDetails from '@/components/workbench/InspectorDetails.vue'
import type { ArtifactVerification } from '@/workbench/runtime/artifactProjection'
const props = defineProps<{ verification?: ArtifactVerification | null }>()
const labels: Record<string, string> = { partial: '部分通过', passed: '通过', failed: '未通过', unknown: '状态未明确' }
const statusLabel = computed(() => props.verification
  ? labels[props.verification.status] || `状态未识别（${props.verification.status}）`
  : '未提供验证结果')
</script>

<style scoped>
.artifact-verification { margin-top: 16px; padding: 12px 16px; border-left: 2px solid var(--wb-text-muted); background: var(--wb-surface-inset); border-radius: 6px; color: var(--wb-text-secondary); font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.artifact-verification.is-warning { border-left-color: var(--wb-warning); }
.artifact-verification > strong { color: var(--wb-text); }
.artifact-verification p { margin: 5px 0; }
.artifact-verification ol, .artifact-verification ul { margin: 0; padding-left: 20px; }
.artifact-verification li + li { margin-top: 10px; }
</style>
