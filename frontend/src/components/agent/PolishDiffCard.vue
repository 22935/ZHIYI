<!-- 润色对比卡片 — 并排展示原文与润色后文本，以及编号的具体修改清单 -->
<template>
  <section class="card polish-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><MagicStick /></el-icon>
        <h4>润色对比</h4>
      </div>
      <span class="change-count" v-if="changes?.length">{{ changes.length }} 处修改</span>
    </header>

    <div v-if="!original && !polished && !changes?.length" class="empty">
      <div class="empty-illustration">
        <el-icon><Document /></el-icon>
      </div>
      <span>暂无润色结果</span>
    </div>

    <template v-else>
      <div v-if="original" class="text-block original-block">
        <div class="block-label">
          <el-icon><Document /></el-icon>
          原文
        </div>
        <p class="text-content">{{ original }}</p>
      </div>

      <div v-if="polished" class="text-block polished-block">
        <div class="block-label">
          <el-icon><MagicStick /></el-icon>
          润色后
        </div>
        <p class="text-content">{{ polished }}</p>
      </div>

      <div v-if="changes?.length" class="changes-section">
        <div class="section-label">
          <el-icon><EditPen /></el-icon>
          修改明细
        </div>
        <div class="changes-list">
          <div
            v-for="(change, idx) in changes"
            :key="idx"
            class="change-item"
            :class="changeTypeClass(change.type)"
          >
            <div class="change-head">
              <span class="change-type-badge" :class="changeTypeClass(change.type)">
                {{ changeTypeLabel(change.type) }}
              </span>
              <span class="change-reason" v-if="change.reason">{{ change.reason }}</span>
            </div>
            <div class="change-diff">
              <span class="diff-old">{{ change.old || change.before }}</span>
              <span class="diff-arrow">→</span>
              <span class="diff-new">{{ change.new || change.after }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="overallComment" class="comment-block">
        <div class="comment-label">
          <el-icon><ChatDotRound /></el-icon>
          总体评价
        </div>
        <p class="comment-text">{{ overallComment }}</p>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChatDotRound, Document, EditPen, MagicStick } from '@element-plus/icons-vue'

interface TextChange {
  type?: string
  old?: string
  before?: string
  new?: string
  after?: string
  reason?: string
}

const props = defineProps<{
  data?: {
    original?: string
    polished?: string
    changes?: TextChange[]
    overall_comment?: string
    overallComment?: string
  }
}>()

const original = computed(() => props.data?.original)
const polished = computed(() => props.data?.polished)
const changes = computed(() => props.data?.changes)
const overallComment = computed(() => props.data?.overall_comment || props.data?.overallComment)

const changeTypeClass = (type?: string) => {
  const t = (type || '').toLowerCase()
  if (t === 'grammar' || t === 'error') return 'grammar'
  if (t === 'style' || t === 'tone') return 'style'
  if (t === 'clarity' || t === 'conciseness') return 'clarity'
  return 'enhance'
}

const changeTypeLabel = (type?: string) => {
  const t = (type || '').toLowerCase()
  if (t === 'grammar') return '语法'
  if (t === 'error') return '纠错'
  if (t === 'style') return '风格'
  if (t === 'tone') return '语气'
  if (t === 'clarity') return '清晰度'
  if (t === 'conciseness') return '简洁性'
  return '润色'
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

.change-count {
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 10px;
  background: var(--warning-fade);
  color: #92400e;
  font-weight: 600;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 24px 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.empty-illustration {
  opacity: 0.7;
  margin-bottom: 4px;
}

.text-block {
  padding: 10px 12px;
}

.original-block {
  background: var(--bg-input);
  border-bottom: 1px solid var(--border-light);
}

.polished-block {
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
  border-bottom: 1px solid #fde68a;
}

.block-label {
  font-size: 11px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 4px;
}

.text-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
}

.changes-section {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
}

.section-label {
  font-size: 11px;
  font-weight: 700;
  color: #d97706;
  margin-bottom: 6px;
}

.changes-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.change-item {
  border-radius: 10px;
  padding: 8px 10px;
  border: 1px solid;
  transition: transform 0.15s ease;
}

.change-item:hover {
  transform: translateX(2px);
}

.change-item.grammar {
  background: linear-gradient(135deg, var(--danger-fade), var(--danger-fade));
  border-color: #fca5a5;
}

.change-item.style {
  background: linear-gradient(135deg, var(--accent-fade), var(--accent-fade));
  border-color: #c4b5fd;
}

.change-item.clarity {
  background: linear-gradient(135deg, var(--primary-fade), var(--primary-fade));
  border-color: #93c5fd;
}

.change-item.enhance {
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
  border-color: #fcd34d;
}

.change-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.change-type-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
}

.change-type-badge.grammar {
  background: var(--danger-fade);
  color: #991b1b;
}

.change-type-badge.style {
  background: var(--accent-fade);
  color: #5b21b6;
}

.change-type-badge.clarity {
  background: var(--primary-fade);
  color: #1e40af;
}

.change-type-badge.enhance {
  background: var(--warning-fade);
  color: #92400e;
}

.change-reason {
  font-size: 11px;
  color: var(--text-secondary);
}

.change-diff {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  flex-wrap: wrap;
}

.diff-old {
  padding: 2px 6px;
  background: var(--danger-fade);
  color: #991b1b;
  border-radius: 4px;
  text-decoration: line-through;
}

.diff-arrow {
  color: var(--text-secondary);
  font-weight: 700;
}

.diff-new {
  padding: 2px 6px;
  background: var(--success-fade);
  color: #166534;
  border-radius: 4px;
  font-weight: 600;
}

.comment-block {
  padding: 10px 12px;
  background: #fffdf5;
}

.comment-label {
  font-size: 11px;
  font-weight: 700;
  color: #d97706;
  margin-bottom: 4px;
}

.comment-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary);
}
</style>
