<template>
  <Teleport to="body">
    <Transition name="role-switcher-fade">
      <div
        v-if="open"
        class="role-switcher-layer"
        role="presentation"
        @click.self="emit('close')"
        @keydown.esc="emit('close')"
      >
        <section
          ref="dialogRef"
          class="role-switcher-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="role-switcher-title"
          tabindex="-1"
        >
          <header class="role-switcher-head">
            <div>
              <span>角色模板</span>
              <h2 id="role-switcher-title">选择角色与模板</h2>
            </div>
            <button type="button" aria-label="关闭角色选择弹窗" @click="emit('close')">×</button>
          </header>

          <div class="role-switcher-body">
            <nav class="role-switcher-roles" aria-label="选择角色">
              <button
                v-for="role in switchableRoleGroups"
                :key="role.id"
                type="button"
                :class="['role-option', `role-option--${role.id}`, { active: pendingRoleId === role.id }]"
                :aria-pressed="pendingRoleId === role.id"
                @click="selectRole(role.id)"
              >
                <span class="role-option__icon">{{ role.short }}</span>
                <span class="role-option__copy">
                  <strong>{{ role.name }}</strong>
                  <small>{{ role.summary }}</small>
                  <em>{{ role.tone }}</em>
                </span>
                <span v-if="currentGroup?.id === role.id" class="role-option__current">当前</span>
              </button>
            </nav>

            <section class="role-switcher-templates" aria-label="选择模板">
              <button
                v-for="template in pendingRole.templates"
                :key="template.key"
                type="button"
                :class="{ active: pendingTemplateKey === template.key }"
                :aria-pressed="pendingTemplateKey === template.key"
                @click="pendingTemplateKey = template.key"
              >
                <span>
                  <strong>{{ template.name }}</strong>
                  <small>{{ template.brief }}</small>
                </span>
                <em>{{ template.key === currentTemplateKey ? '当前' : '预览' }}</em>
              </button>
            </section>

            <aside class="role-switcher-preview" aria-label="模板预览">
              <span class="preview-eyebrow">{{ pendingRole.name }} Agent</span>
              <h3>{{ pendingTemplate.name }}</h3>
              <p>{{ pendingTemplate.subtitle }}</p>
              <div class="preview-meta">
                <span>{{ pendingTemplate.runtimeLabel }}</span>
                <span>{{ pendingTemplate.workflowId }}</span>
              </div>
              <div class="preview-flow" aria-label="工作流步骤">
                <span v-for="step in pendingTemplate.steps" :key="step.id">{{ step.title }}</span>
              </div>
              <dl>
                <div><dt>输出</dt><dd>{{ pendingTemplate.outputTitle }}</dd></div>
                <div><dt>Workflow</dt><dd>{{ pendingTemplate.workflowLabel }}</dd></div>
                <div><dt>Domain</dt><dd>{{ pendingTemplate.domain }}</dd></div>
              </dl>
            </aside>
          </div>

          <footer class="role-switcher-footer">
            <span>切换角色或模板会创建新上下文；当前任务仍保留在历史记录中。</span>
            <div>
              <button type="button" class="role-switcher-cancel" @click="emit('close')">取消</button>
              <button type="button" class="role-switcher-confirm" @click="confirmSelection">
                <span aria-hidden="true">✓</span>
                确定
              </button>
            </div>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { roleTemplateGroups, type RoleId } from '@/config/agentWorkbench'

type SwitchableRoleId = RoleId | 'general'

const generalRoleGroup = {
  id: 'general' as const,
  name: '通用模式',
  short: '通',
  summary: '不绑定垂直角色，适合跨领域问答与复杂任务',
  tone: '动态路由',
  templates: [{
    key: 'general-auto',
    name: '通用智能协作',
    brief: '根据任务复杂度自动选择直接对话或 ACG 动态规划',
    subtitle: '日常问题快速响应，复杂任务自动拆解、协作执行并形成交付。',
    runtimeLabel: '智能路由',
    workflowId: '动态规划',
    steps: [
      { id: 'understand', title: '理解意图' },
      { id: 'route', title: '动态路由' },
      { id: 'deliver', title: '生成交付' }
    ],
    outputTitle: '与任务匹配的回答或交付物',
    workflowLabel: '按需启用 ACG',
    domain: 'general'
  }]
}

const switchableRoleGroups = [generalRoleGroup, ...roleTemplateGroups]

const props = defineProps<{
  open: boolean
  currentRoleName?: string
  currentTemplateKey?: string
}>()

const emit = defineEmits<{
  close: []
  confirm: [selection: { roleId: SwitchableRoleId; templateKey: string }]
}>()

const dialogRef = ref<HTMLElement | null>(null)
const pendingRoleId = ref<SwitchableRoleId>('general')
const pendingTemplateKey = ref(generalRoleGroup.templates[0].key)

const roleAliases: Record<RoleId, string[]> = {
  lawyer: ['律师', '法律', 'lawyer'],
  teacher: ['教师', '教学', 'teacher'],
  programmer: ['程序', '开发', 'programmer', 'developer'],
  writer: ['作家', '写作', 'writer']
}

const currentGroup = computed(() => {
  const name = (props.currentRoleName || '').toLowerCase()
  if (!name) return generalRoleGroup
  return roleTemplateGroups.find(role => roleAliases[role.id].some(alias => name.includes(alias))) || generalRoleGroup
})
const pendingRole = computed(() => switchableRoleGroups.find(role => role.id === pendingRoleId.value) || generalRoleGroup)
const pendingTemplate = computed(() => pendingRole.value.templates.find(item => item.key === pendingTemplateKey.value) || pendingRole.value.templates[0])

const selectRole = (roleId: SwitchableRoleId) => {
  pendingRoleId.value = roleId
  pendingTemplateKey.value = switchableRoleGroups.find(role => role.id === roleId)?.templates[0].key || ''
}

const confirmSelection = () => {
  emit('confirm', { roleId: pendingRole.value.id, templateKey: pendingTemplate.value.key })
}

watch(
  () => props.open,
  async visible => {
    if (!visible) return
    const role = currentGroup.value || generalRoleGroup
    pendingRoleId.value = role.id
    pendingTemplateKey.value = role.templates.some(item => item.key === props.currentTemplateKey)
      ? props.currentTemplateKey!
      : role.templates[0].key
    await nextTick()
    dialogRef.value?.focus()
  }
)
</script>

<style scoped>
.role-switcher-layer {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: color-mix(in srgb, var(--bg-app) 38%, transparent);
  backdrop-filter: blur(12px);
}

.role-switcher-dialog {
  width: min(1120px, 94vw);
  max-height: min(820px, 90vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--text-primary);
  background: color-mix(in srgb, var(--bg-card) 96%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, var(--border-light));
  border-radius: 18px;
  box-shadow: 0 26px 80px color-mix(in srgb, var(--text-primary) 24%, transparent);
  outline: none;
}

.role-switcher-head,
.role-switcher-footer {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 24px;
}

.role-switcher-head { border-bottom: 1px solid var(--border-light); }
.role-switcher-head span { color: var(--primary-color); font-size: 12px; font-weight: 700; }
.role-switcher-head h2 { margin: 5px 0 0; font-size: 22px; }
.role-switcher-head > button {
  width: 38px;
  height: 38px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  color: var(--text-secondary);
  background: transparent;
  font-size: 22px;
  cursor: pointer;
}

.role-switcher-body {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(240px, 0.9fr) minmax(280px, 1.05fr) minmax(300px, 1.15fr);
  gap: 24px;
  padding: 20px;
  overflow: auto;
}

.role-switcher-roles,
.role-switcher-templates {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.role-option,
.role-switcher-templates button {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 14px;
  text-align: left;
  color: var(--text-primary);
  background: color-mix(in srgb, var(--bg-card) 78%, var(--bg-app));
  border: 1px solid var(--border-light);
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
}

.role-option:hover,
.role-switcher-templates button:hover { transform: translateY(-1px); border-color: var(--primary-color); }
.role-option.active,
.role-switcher-templates button.active {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 9%, var(--bg-card));
  box-shadow: inset 3px 0 0 var(--primary-color);
}

.role-option__icon {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  color: var(--role-tone, var(--primary-color));
  background: color-mix(in srgb, var(--role-tone, var(--primary-color)) 14%, var(--bg-card));
  font-weight: 800;
}
.role-option--lawyer { --role-tone: var(--info); }
.role-option--general { --role-tone: var(--primary-color); }
.role-option--teacher { --role-tone: var(--success); }
.role-option--programmer { --role-tone: var(--accent-color); }
.role-option--writer { --role-tone: var(--warning); }
.role-option__copy { min-width: 0; display: grid; gap: 4px; }
.role-option__copy strong { font-size: 15px; }
.role-option__copy small { color: var(--text-secondary); line-height: 1.5; }
.role-option__copy em { color: var(--role-tone); font-size: 12px; font-style: normal; font-weight: 700; }
.role-option__current {
  margin-left: auto;
  padding: 3px 7px;
  border-radius: 999px;
  color: var(--primary-color);
  background: var(--primary-fade);
  font-size: 11px;
}

.role-switcher-templates button { justify-content: space-between; align-items: center; min-height: 60px; }
.role-switcher-templates button > span { min-width: 0; display: grid; gap: 4px; }
.role-switcher-templates strong { font-size: 14px; }
.role-switcher-templates small { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.role-switcher-templates em { flex: 0 0 auto; color: var(--primary-color); font-size: 11px; font-style: normal; }

.role-switcher-preview {
  min-width: 0;
  padding: 18px;
  background: color-mix(in srgb, var(--bg-app) 66%, var(--bg-card));
  border: 1px solid var(--border-light);
  border-radius: 14px;
}
.preview-eyebrow { color: var(--primary-color); font-size: 12px; font-weight: 700; }
.role-switcher-preview h3 { margin: 10px 0 8px; font-size: 20px; }
.role-switcher-preview p { margin: 0; color: var(--text-secondary); line-height: 1.65; }
.preview-meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.preview-meta span { padding: 5px 9px; border-radius: 999px; color: var(--primary-color); background: var(--primary-fade); font-size: 11px; }
.preview-flow { display: grid; gap: 8px; margin: 14px 0 18px; }
.preview-flow span { padding: 9px 10px; border-radius: 8px; color: var(--text-primary); background: color-mix(in srgb, var(--primary-color) 8%, var(--bg-card)); border: 1px solid var(--border-light); }
.role-switcher-preview dl { display: grid; gap: 8px; margin: 0; }
.role-switcher-preview dl div { padding: 10px; border-radius: 9px; background: color-mix(in srgb, var(--bg-card) 82%, transparent); }
.role-switcher-preview dt { color: var(--text-secondary); font-size: 11px; }
.role-switcher-preview dd { margin: 4px 0 0; overflow-wrap: anywhere; font-size: 13px; }

.role-switcher-footer { border-top: 1px solid var(--border-light); }
.role-switcher-footer > span { color: var(--text-secondary); font-size: 12px; }
.role-switcher-footer > div { display: flex; gap: 10px; }
.role-switcher-footer button { min-width: 86px; padding: 10px 18px; border-radius: 9px; cursor: pointer; }
.role-switcher-cancel { color: var(--text-secondary); background: transparent; border: 1px solid var(--border-light); }
.role-switcher-confirm { color: var(--text-on-primary, #fff); background: var(--primary-color); border: 1px solid var(--primary-color); font-weight: 700; }

.role-switcher-fade-enter-active,
.role-switcher-fade-leave-active { transition: opacity 160ms ease; }
.role-switcher-fade-enter-active .role-switcher-dialog,
.role-switcher-fade-leave-active .role-switcher-dialog { transition: transform 180ms ease, opacity 180ms ease; }
.role-switcher-fade-enter-from,
.role-switcher-fade-leave-to { opacity: 0; }
.role-switcher-fade-enter-from .role-switcher-dialog,
.role-switcher-fade-leave-to .role-switcher-dialog { opacity: 0; transform: translateY(10px) scale(0.985); }

@media (max-width: 900px) {
  .role-switcher-body { grid-template-columns: 1fr 1fr; }
  .role-switcher-preview { grid-column: 1 / -1; }
}

@media (max-width: 640px) {
  .role-switcher-layer { padding: 10px; }
  .role-switcher-dialog { width: 100%; max-height: 96vh; }
  .role-switcher-body { grid-template-columns: 1fr; gap: 14px; padding: 14px; }
  .role-switcher-preview { grid-column: auto; }
  .role-switcher-footer { align-items: stretch; flex-direction: column; }
  .role-switcher-footer > div { justify-content: flex-end; }
}

@media (prefers-reduced-motion: reduce) {
  .role-option,
  .role-switcher-templates button,
  .role-switcher-fade-enter-active,
  .role-switcher-fade-leave-active { transition: none; }
}
</style>
