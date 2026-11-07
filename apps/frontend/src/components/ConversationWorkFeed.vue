<!-- 对话工作流侧栏 — 命令/文件执行与审批聚合展示（迁移自主对话区，主区只保留思考与输出） -->
<template>
  <div class="work-feed">
    <div v-if="!items.length" class="work-feed__empty">本轮对话暂无命令与文件执行记录</div>
    <template v-else>
      <section v-if="approvalActivities.length" class="approval-work" aria-label="执行审批">
        <article
          v-for="item in approvalActivities"
          :key="`approval-${item.approval?.approvalId}`"
          class="approval-work__card"
          :class="{ 'is-resolved': item.approval?.status !== 'pending' }"
        >
          <div class="approval-work__title">
            {{ item.approval?.operation === 'Run command' ? '需要确认命令执行' : '需要确认文件操作' }}
          </div>
          <div class="approval-work__summary">{{ item.approval?.operationSummary }}</div>
          <div v-if="item.approval?.command" class="approval-work__command">
            <code>$ {{ item.approval.command }}</code>
          </div>
          <div v-if="item.approval?.cwd" class="approval-work__cwd">
            cwd: <code>{{ item.approval.cwd }}</code>
          </div>
          <div v-if="item.approval?.riskNotice" class="approval-work__risk">
            {{ item.approval.riskNotice }}
          </div>
          <div class="approval-work__scope">
            <code>{{ item.approval?.capabilityId }}</code>
            <code v-if="item.approval?.relativePath">{{ item.approval.relativePath }}</code>
          </div>
          <div v-if="item.approval?.status === 'pending'" class="approval-work__actions">
            <button
              type="button"
              class="approval-work__button is-primary"
              :disabled="approvalBusy[item.approval.approvalId]"
              @click="resolveApproval(item, 'allow_once')"
            >允许一次</button>
            <button
              v-if="item.approval?.capabilityId !== 'shell.exec'"
              type="button"
              class="approval-work__button"
              :disabled="approvalBusy[item.approval.approvalId]"
              @click="resolveApproval(item, 'allow_session')"
            >本次会话允许</button>
            <button
              type="button"
              class="approval-work__button is-danger"
              :disabled="approvalBusy[item.approval.approvalId]"
              @click="resolveApproval(item, 'deny')"
            >拒绝</button>
          </div>
          <div v-else class="approval-work__resolved">
            {{ item.approval?.status === 'approved' ? '已允许' : item.approval?.status === 'denied' ? '已拒绝' : '已失效' }}
          </div>
        </article>
      </section>

      <section v-if="terminalActivities.length" class="terminal-work" aria-label="终端工作">
        <div class="terminal-work__header">
          <span class="terminal-work__title">终端工作</span>
          <span class="terminal-work__count">{{ terminalActivities.length }} 次调用</span>
        </div>
        <article
          v-for="item in terminalActivities"
          :key="item.stage"
          class="terminal-work__item"
          :class="{ 'is-failed': item.status === 'failed' || item.status === 'cancelled', 'is-running': item.status === 'running' }"
        >
          <div v-if="item.terminal" class="terminal-work__meta">
            <code class="terminal-work__command">$ {{ item.terminal.command }}</code>
            <span class="terminal-work__cwd">{{ item.terminal.cwd }}</span>
            <span class="terminal-work__exit">
              {{ item.terminal.timedOut ? '超时' : item.terminal.exitCode === null ? '运行中' : `退出码 ${item.terminal.exitCode}` }}
            </span>
          </div>
          <div v-else class="terminal-work__running">
            <!-- 运行中：审批卡里已带命令文本，直接展示；完成后仍无 terminal 载荷（旧数据）则如实标注 -->
            <code v-if="item.approval?.command" class="terminal-work__running-command">$ {{ item.approval.command }}</code>
            <span>{{ item.status === 'completed' || item.status === 'failed' ? '命令已执行，输出未回传' : '正在执行终端命令…' }}</span>
          </div>
          <pre v-if="item.terminal?.stdout" class="terminal-work__output">{{ item.terminal.stdout }}</pre>
          <pre v-if="item.terminal?.stderr" class="terminal-work__output is-stderr">{{ item.terminal.stderr }}</pre>
          <div v-if="item.terminal?.truncated" class="terminal-work__truncated">输出已截断</div>
        </article>
      </section>

      <section v-if="fileActivities.length" class="file-work" aria-label="文件工作">
        <div class="file-work__header">
          <span class="file-work__title">文件工作</span>
          <span class="file-work__count">{{ fileActivities.length }} 次调用</span>
        </div>
        <article
          v-for="item in fileActivities"
          :key="`file-${item.stage}`"
          class="file-work__item"
          :class="{ 'is-failed': item.status === 'failed' || item.status === 'cancelled', 'is-running': item.status === 'running' }"
        >
          <div class="file-work__meta">
            <span class="file-work__kind">{{ fileActivityLabel(item.activity?.kind) }}</span>
            <code v-if="item.activity?.relativePath" class="file-work__path">{{ item.activity.relativePath }}</code>
            <span v-if="item.activity?.entryCount !== undefined" class="file-work__count-detail">
              {{ item.activity.entryCount }} 项
            </span>
          </div>
          <div class="file-work__summary">
            {{ item.activity?.summary || item.description }}
            <span v-if="item.activity?.addedLines !== undefined || item.activity?.removedLines !== undefined">
              （+{{ item.activity?.addedLines || 0 }} / -{{ item.activity?.removedLines || 0 }}）
            </span>
          </div>
          <div v-if="item.status === 'failed'" class="file-work__error">
            执行失败：{{ item.activity?.errorCode || 'FILE_OPERATION_FAILED' }}
          </div>
        </article>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { chatApi, type ChatApprovalDecision } from '@/services/api/chat'

interface TerminalExecution {
  command: string
  cwd: string
  exitCode: number | null
  stdout: string
  stderr: string
  timedOut: boolean
  truncated: boolean
  durationMs?: number
}

interface ToolExecutionActivity {
  kind: string
  capabilityId?: string
  relativePath?: string
  status?: string
  summary?: string
  addedLines?: number
  removedLines?: number
  entryCount?: number
  errorCode?: string
}

interface ChatApproval {
  approvalId: string
  toolCallId: string
  invocationId: string
  toolName: string
  capabilityId: string
  relativePath?: string
  operationSummary: string
  createdAt: string
  status: string
  sessionId: string
  operation?: string
  command?: string
  cwd?: string
  riskNotice?: string
}

interface WorkFeedItem {
  stage: string
  status: string
  description: string
  durationMs?: number
  terminal?: TerminalExecution
  activity?: ToolExecutionActivity
  approval?: ChatApproval
}

interface Props {
  items: WorkFeedItem[]
}

const props = defineProps<Props>()
const approvalBusy = ref<Record<string, boolean>>({})

const terminalActivities = computed(() => props.items
  .filter(item => item.stage.split(':')[1] === 'terminal' || item.stage.split(':')[1] === 'run_command'))

const fileActivities = computed(() => props.items
  .filter(item => item.activity && item.activity.kind !== 'terminal'))

const approvalActivities = computed(() => props.items
  .filter(item => item.approval))

const pendingApprovalCount = computed(() => approvalActivities.value
  .filter(item => item.approval?.status === 'pending').length)
defineExpose({ pendingApprovalCount })

const fileActivityLabel = (kind?: string) => {
  const labels: Record<string, string> = {
    file_read: '读取',
    file_write: '写入',
    file_patch: '修改',
    file_list: '列目录'
  }
  return labels[kind || ''] || kind || '文件操作'
}

const resolveApproval = async (item: WorkFeedItem, decision: ChatApprovalDecision) => {
  const approval = item.approval
  if (!approval || approvalBusy.value[approval.approvalId]) return
  approvalBusy.value = { ...approvalBusy.value, [approval.approvalId]: true }
  try {
    await chatApi.resolveApproval(approval.approvalId, {
      decision,
      sessionId: approval.sessionId,
      invocationId: approval.invocationId,
      capabilityId: approval.capabilityId,
      relativePath: approval.relativePath
    })
  } catch {
    ElMessage.error('审批请求处理失败，请重试')
  } finally {
    const next = { ...approvalBusy.value }
    delete next[approval.approvalId]
    approvalBusy.value = next
  }
}
</script>

<style scoped lang="scss">
.work-feed {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.work-feed__empty {
  padding: 10px 12px;
  color: var(--text-muted);
  font-size: 12px;
}

.approval-work {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.approval-work__card {
  padding: 10px 12px 11px;
  border: 1px solid color-mix(in srgb, var(--warning) 38%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--warning) 7%, var(--bg-panel));
}

.approval-work__card.is-resolved {
  border-color: color-mix(in srgb, var(--border-light) 70%, transparent);
  background: var(--bg-panel);
  opacity: 0.86;
}

.approval-work__title {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
}

.approval-work__summary,
.approval-work__command,
.approval-work__cwd,
.approval-work__risk,
.approval-work__scope,
.approval-work__resolved {
  margin-top: 6px;
  color: var(--text-regular);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.approval-work__command,
.approval-work__cwd {
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
}

.approval-work__risk {
  color: var(--warning);
}

.approval-work__scope {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.approval-work__scope code {
  padding: 2px 6px;
  border: 1px solid color-mix(in srgb, var(--border-light) 70%, transparent);
  border-radius: 5px;
  color: var(--text-secondary);
  font-size: 11px;
}

.approval-work__actions {
  display: flex;
  gap: 8px;
  margin-top: 9px;
}

.approval-work__button {
  padding: 4px 10px;
  border: 1px solid color-mix(in srgb, var(--border-light) 75%, transparent);
  border-radius: 7px;
  background: transparent;
  color: var(--text-regular);
  font-size: 12px;
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease, border-color 140ms ease;
}

.approval-work__button.is-primary {
  border-color: color-mix(in srgb, var(--primary-color) 45%, transparent);
  color: var(--primary-color);
}

.approval-work__button.is-danger {
  border-color: color-mix(in srgb, var(--danger) 45%, transparent);
  color: var(--danger);
}

.approval-work__button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.terminal-work {
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--border-light) 88%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--bg-panel) 86%, #101317);
}

.terminal-work__header,
.terminal-work__meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.terminal-work__header {
  justify-content: space-between;
  padding: 8px 11px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-light) 78%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
}

.terminal-work__title { color: var(--text-primary); font-weight: 600; }
.terminal-work__count,
.terminal-work__cwd,
.terminal-work__exit { color: var(--text-muted); font-size: 11px; }

.terminal-work__item {
  padding: 9px 11px 10px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-light) 62%, transparent);
}

.terminal-work__item:last-child { border-bottom: 0; }
.terminal-work__item.is-failed { background: color-mix(in srgb, var(--danger) 5%, transparent); }
.terminal-work__item.is-running { background: color-mix(in srgb, var(--primary-color) 4%, transparent); }

.terminal-work__meta {
  flex-wrap: wrap;
  line-height: 1.45;
}

.terminal-work__command {
  color: var(--text-primary);
  font: 12px/1.5 var(--font-mono, monospace);
  overflow-wrap: anywhere;
  text-align: left;
}

.terminal-work__cwd { overflow-wrap: anywhere; }

.terminal-work__exit {
  margin-left: auto;
  color: var(--success);
}

.terminal-work__item.is-failed .terminal-work__exit { color: var(--danger); }
.terminal-work__running {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}

.terminal-work__running-command {
  color: var(--text-primary);
  font: 12px/1.5 var(--font-mono, monospace);
  overflow-wrap: anywhere;
  text-align: left;
}

.terminal-work__output {
  max-height: 220px;
  margin: 8px 0 0;
  padding: 9px 10px;
  overflow: auto;
  border: 1px solid color-mix(in srgb, var(--border-light) 60%, transparent);
  border-radius: 6px;
  color: #d7e2ea;
  background: #101317;
  font: 12px/1.55 var(--font-mono, monospace);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.terminal-work__output.is-stderr { color: #f0b7ad; }
.terminal-work__truncated { margin-top: 6px; color: var(--warning); font-size: 11px; }

.file-work {
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--border-light) 88%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--bg-panel) 86%, #101317);
}

.file-work__header,
.file-work__meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-work__header {
  justify-content: space-between;
  padding: 8px 11px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-light) 78%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
}

.file-work__title { color: var(--text-primary); font-weight: 600; }
.file-work__count,
.file-work__count-detail { color: var(--text-muted); font-size: 11px; }
.file-work__item { padding: 9px 11px 10px; border-bottom: 1px solid color-mix(in srgb, var(--border-light) 62%, transparent); }
.file-work__item:last-child { border-bottom: 0; }
.file-work__item.is-failed { background: color-mix(in srgb, var(--danger) 5%, transparent); }
.file-work__item.is-running { background: color-mix(in srgb, var(--primary-color) 4%, transparent); }
.file-work__meta { flex-wrap: wrap; line-height: 1.45; }
.file-work__kind { color: var(--text-secondary); font-size: 12px; }
.file-work__path { color: var(--text-primary); font: 12px/1.5 var(--font-mono, monospace); overflow-wrap: anywhere; }
.file-work__summary { margin-top: 5px; color: var(--text-regular); font-size: 12px; }
.file-work__error { margin-top: 5px; color: var(--danger); font-size: 11px; }
</style>
