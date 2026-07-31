<!-- 题目推送列表 — 错因归因和题目推送，含知识缺口标签、分析摘要和推荐练习题列表 -->
<template>
  <section class="card push-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Aim /></el-icon>
        <h4>错题归因与推题</h4>
      </div>
      <span class="count">推题 {{ questions.length }}</span>
    </header>

    <div class="block">
      <div class="title gap-title">知识漏洞</div>
      <div v-if="knowledgeGap.length" class="gap-tags">
        <span v-for="item in knowledgeGap" :key="item" class="gap-tag">{{ item }}</span>
      </div>
      <div v-else class="empty">暂无知识漏洞信息</div>
    </div>

    <div class="block">
      <div class="title analysis-title">归因总结</div>
      <p class="text analysis-text">{{ data?.analysis_summary || '暂无归因总结。' }}</p>
    </div>

    <div class="block">
      <div class="title question-title">推荐练习题</div>
      <div v-if="questions.length" class="question-list">
        <div class="question-item" v-for="(item, idx) in questions" :key="item.id || idx">
          <div class="q-header">
            <span class="q-index">{{ idx + 1 }}</span>
            <span class="q-difficulty" :class="difficultyClass(item.difficulty)">{{ item.difficulty || '中等' }}</span>
          </div>
          <div class="q-text">{{ item.question_text || item.question || '未提供题干' }}</div>
          <div class="q-meta">
            <span v-if="item.question_type" class="meta-tag type-tag">{{ item.question_type }}</span>
            <span v-if="item.subject" class="meta-tag subject-tag">{{ item.subject }}</span>
          </div>
        </div>
      </div>
      <div v-else class="empty">暂无推荐题目</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Aim } from '@element-plus/icons-vue'

interface SimilarQuestion {
  id?: string
  question_text?: string
  question?: string
  difficulty?: string
  question_type?: string
  subject?: string
}

interface ErrorPushData {
  knowledge_gap?: string[]
  analysis_summary?: string
  similar_questions?: SimilarQuestion[]
}

const props = defineProps<{ data?: ErrorPushData }>()

const knowledgeGap = computed(() => props.data?.knowledge_gap || [])
const questions = computed(() => props.data?.similar_questions || [])

const difficultyClass = (difficulty?: string) => {
  const d = (difficulty || '').toLowerCase()
  if (d.includes('难') || d.includes('hard') || d.includes('高')) return 'hard'
  if (d.includes('易') || d.includes('easy') || d.includes('低')) return 'easy'
  return 'medium'
}
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-solid);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.head-icon {
  font-size: 16px;
}

.card-head h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
}

.count {
  font-size: 12px;
  color: #059669;
  background: var(--success-fade);
  border: 1px solid #a7f3d0;
  border-radius: 999px;
  padding: 3px 10px;
  font-weight: 600;
}

.block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
}

.gap-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.gap-tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--warning-fade);
  color: #92400e;
  border: 1px solid #fcd34d;
  font-weight: 500;
}

.analysis-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  padding: 8px 10px;
  background: var(--warning-fade);
  border-radius: 8px;
  border-left: 3px solid #d97706;
}

.question-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.question-item {
  border: 1px solid #d1fae5;
  background: linear-gradient(135deg, var(--success-fade), var(--success-fade));
  border-radius: 10px;
  padding: 10px 12px;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.question-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(5, 150, 105, 0.1);
}

.q-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.q-index {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: var(--success);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.q-difficulty {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 500;
}

.q-difficulty.easy {
  background: var(--success-fade);
  color: #166534;
}

.q-difficulty.medium {
  background: var(--warning-fade);
  color: #92400e;
}

.q-difficulty.hard {
  background: var(--danger-fade);
  color: #b91c1c;
}

.q-text {
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-primary);
}

.q-meta {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.meta-tag {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 500;
}

.type-tag {
  background: var(--accent-fade);
  color: #3730a3;
}

.subject-tag {
  background: var(--success-fade);
  color: #047857;
}

.empty {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
