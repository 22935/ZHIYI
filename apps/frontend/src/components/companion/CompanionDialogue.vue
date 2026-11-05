<template>
  <div class="companion-dialogue" data-testid="companion-dialogue">
    <div class="companion-quick">
      <button
        v-for="item in quick"
        :key="item.id"
        type="button"
        class="companion-quick-btn"
        :data-testid="`companion-quick-${item.id}`"
        @click="emit('send', item.text)"
      >{{ item.label }}</button>
    </div>

    <div class="companion-messages" data-testid="companion-messages">
      <p v-if="!messages.length" class="companion-empty">问我进度、聊两句，或者让我整理一张任务卡。</p>
      <div
        v-for="message in messages"
        :key="message.id"
        class="companion-msg"
        :class="`companion-msg--${message.role}`"
      >{{ message.content }}</div>
      <div v-if="pending" class="companion-msg companion-msg--companion">正在想…</div>
    </div>

    <div v-if="card" class="companion-card" data-testid="companion-card">
      <span class="companion-card-title">任务意图卡</span>
      <span class="companion-card-body">{{ card.title }}</span>
      <span class="companion-card-note">{{ card.note }}</span>
      <button type="button" data-testid="companion-card-close" @click="emit('dismiss-card')">知道了</button>
    </div>

    <form class="companion-input-row" @submit.prevent="submit">
      <input
        v-model="draft"
        type="text"
        data-testid="companion-input"
        aria-label="和虚拟伙伴说话"
        placeholder="说点什么…"
        :disabled="pending"
      />
      <button type="submit" data-testid="companion-send" :disabled="pending || !draft.trim()">发送</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { CompanionMessage, TaskIntentCard } from '@/features/companion/types'

defineProps<{
  messages: CompanionMessage[]
  pending: boolean
  card: TaskIntentCard | null
}>()

const emit = defineEmits<{
  (event: 'send', text: string): void
  (event: 'dismiss-card'): void
}>()

const draft = ref('')
const quick = [
  { id: 'progress', label: '查进度', text: '现在的任务进度怎么样了？' },
  { id: 'chat', label: '聊两句', text: '你好，在吗？' },
  { id: 'emotion', label: '有点累', text: '今天好累啊' },
  { id: 'task', label: '记个任务', text: '帮我新建一个合同审查任务' }
]

const submit = () => {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  emit('send', text)
}
</script>

<style scoped>
.companion-dialogue { display: flex; flex-direction: column; gap: 8px; }
.companion-quick { display: flex; flex-wrap: wrap; gap: 4px; }
.companion-quick-btn, .companion-input-row button, .companion-card button {
  font: inherit; font-size: 12px; padding: 4px 8px; cursor: pointer;
  color: var(--text-regular, var(--text-primary)); background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px;
  transition: background-color 180ms ease;
}
.companion-quick-btn:hover, .companion-input-row button:hover { background: var(--surface-hover, var(--bg-panel)); }
.companion-messages {
  max-height: 208px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;
  padding: 8px; background: var(--bg-input, var(--bg-app)); border-radius: 8px;
}
.companion-empty { margin: 0; font-size: 12px; color: var(--text-muted, var(--text-secondary)); line-height: 1.6; }
.companion-msg { font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.companion-msg--user { align-self: flex-end; max-width: 86%; padding: 6px 9px; border-radius: 8px; background: var(--accent-fade, var(--primary-fade)); }
.companion-msg--companion { align-self: flex-start; max-width: 92%; color: var(--text-regular, var(--text-primary)); }
.companion-card { display: flex; flex-direction: column; gap: 4px; padding: 8px; border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 8px; }
.companion-card-title { font-size: 12px; font-weight: 500; }
.companion-card-body { font-size: 13px; }
.companion-card-note { font-size: 11px; color: var(--text-muted, var(--text-secondary)); line-height: 1.5; }
.companion-card button { align-self: flex-start; }
.companion-input-row { display: flex; gap: 6px; }
.companion-input-row input {
  flex: 1; min-width: 0; font: inherit; font-size: 12px; padding: 6px 8px;
  color: var(--text-primary); background: var(--bg-input, var(--bg-app));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px; outline: none;
}
.companion-input-row button:disabled, .companion-quick-btn:disabled { opacity: 0.5; cursor: default; }
@media (prefers-reduced-motion: reduce) { .companion-quick-btn, .companion-input-row button { transition: none; } }
</style>
