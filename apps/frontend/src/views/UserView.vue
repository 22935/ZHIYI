<!-- 个人中心页面：导航由应用级侧栏统一承载，主体聚焦身份、活动与资料。 -->
<template>
  <div class="user-view">
    <main class="user-content">
      <header class="content-header">
        <div>
          <button class="back-to-app" type="button" @click="goBack">
            <el-icon><ArrowLeft /></el-icon>
            返回
          </button>
          <span class="content-eyebrow">PROFILE</span>
          <h1>个人资料</h1>
        </div>
        <div class="content-actions">
          <button class="profile-action" type="button" @click="inviteFriend"><el-icon><Promotion /></el-icon>邀请好友</button>
          <button class="profile-action" type="button" @click="shareProfile"><el-icon><Share /></el-icon>分享</button>
          <span class="profile-action profile-status"><el-icon><Lock /></el-icon>私有</span>
          <button class="profile-action" type="button" @click="editing = !editing"><el-icon><Edit /></el-icon>{{ editing ? '完成编辑' : '编辑' }}</button>
        </div>
      </header>


        <section class="identity-hero">
          <button class="avatar-uploader" type="button" :disabled="avatarUploading" @click="openAvatarPicker">
            <span class="hero-avatar">
              <img v-if="avatarSrc" :src="avatarSrc" alt="用户头像" />
              <el-icon v-else :size="38"><User /></el-icon>
              <span class="avatar-edit" title="更换头像"><el-icon :size="11"><Camera /></el-icon></span>
            </span>
          </button>
          <input ref="avatarInput" class="avatar-input" type="file" accept="image/jpeg,image/png,image/webp,image/gif" @change="handleAvatarChange" />
          <p class="avatar-hint">{{ avatarUploading ? '正在上传头像…' : '点击头像更换 · JPG、PNG、WebP 或 GIF，最大 5MB' }}</p>
          <h2 class="hero-name">{{ userInfo.username || '—' }}</h2>
          <p class="hero-handle"><span>@{{ userInfo.email || '未设置邮箱' }}</span><span class="hero-badge">{{ roleBadge }}</span></p>
        </section>

        <section class="stats-row" aria-label="账户统计">
          <div v-for="stat in profileStats" :key="stat.label" class="stats-cell"><strong>{{ stat.value }}</strong><span>{{ stat.label }}</span></div>
        </section>

        <section class="activity-card" aria-labelledby="activity-title">
          <header class="activity-card__header">
            <div><span class="card-kicker">ACTIVITY</span><h2 id="activity-title">{{ activityTitle }}</h2><p>{{ activityCaption }}</p></div>
            <div class="activity-modes" role="tablist" aria-label="活动时间粒度">
              <button v-for="mode in activityModes" :key="mode.id" class="activity-mode" :class="{ active: activityMode === mode.id }" type="button" role="tab" :aria-selected="activityMode === mode.id" @click="activityMode = mode.id">{{ mode.label }}</button>
            </div>
          </header>
          <div class="activity-chart" :class="{ loading: activityLoading }">
            <div class="activity-months" aria-hidden="true"><span v-for="marker in monthMarkers" :key="marker.label + '-' + marker.index" :style="{ gridColumn: marker.index + 1 }">{{ marker.label }}</span></div>
            <div class="activity-grid-shell">
              <div class="weekday-labels" aria-hidden="true"><span>一</span><span>三</span><span>五</span></div>
              <div class="heatmap-grid" role="grid" :aria-label="activityTitle + '，最近一年'">
                <div v-for="column in heatmapColumns" :key="column.key" class="heatmap-week" role="row">
                  <button v-for="cell in column.days" :key="cell.key" class="heatmap-cell" :class="['level-' + cell.level, { today: cell.isToday, future: cell.isFuture }]" type="button" role="gridcell" :aria-label="cell.label" :title="cell.label"></button>
                </div>
              </div>
            </div>
            <div class="activity-legend"><span>{{ activityMode === 'weekly' ? '低' : '较少' }}</span><span class="legend-swatches"><i v-for="level in 5" :key="level" class="heatmap-cell" :class="'level-' + (level - 1)"></i></span><span>{{ activityMode === 'weekly' ? '高' : '更多' }}</span></div>
          </div>
          <footer class="activity-card__footer"><span>{{ activitySummary }}</span><span v-if="activityTokenTotal">已观测 {{ formatCompactNumber(activityTokenTotal) }} Token</span><span v-else>按已记录的对话与运行活动统计</span></footer>
        </section>

        <section class="detail-grid">
          <article class="detail-card">
            <header class="detail-card__header"><span class="card-kicker">ACCOUNT</span><h3>账户信息</h3></header>
            <dl class="insight-list"><div class="insight-row"><dt>用户名</dt><dd>{{ userInfo.username || '—' }}</dd></div><div class="insight-row"><dt>邮箱地址</dt><dd>{{ userInfo.email || '未设置' }}</dd></div><div class="insight-row"><dt>注册时间</dt><dd>{{ formatDate(userInfo.createdAt) }}</dd></div></dl>
          </article>
          <article class="detail-card">
            <header class="detail-card__header"><span class="card-kicker">PROFILE</span><h3>编辑资料</h3></header>
            <div class="detail-card__body">
              <el-form :model="userInfo" label-position="top" class="user-form">
                <el-form-item label="用户名"><el-input v-model="userInfo.username" disabled class="custom-input" /><div class="form-hint">用户名不可修改</div></el-form-item>
                <el-form-item label="邮箱地址"><el-input v-model="userInfo.email" :disabled="!editing" placeholder="请输入邮箱地址" class="custom-input" /><div class="form-hint">用于个人资料展示</div></el-form-item>
                <el-form-item><el-button type="primary" :disabled="!editing" @click="updateProfile"><el-icon><Check /></el-icon>保存更改</el-button></el-form-item>
              </el-form>
            </div>
          </article>
        </section>

    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Camera, Check, Edit, Lock, Promotion, Share, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { userApi } from '@/services/api/user'
import { conversationApi, type Conversation } from '@/services/api/conversation'
import { workflowApi, type WorkflowRunSummary } from '@/services/api/workflow'

type ActivityMode = 'daily' | 'weekly' | 'total'
type ActivityRecord = { date: string; events: number; tokens: number }
type ActivityDay = { key: string; label: string; level: number; isToday: boolean; isFuture: boolean }
type ActivityColumn = { key: string; days: ActivityDay[] }

const router = useRouter()

const goBack = () => {
  if (window.history.length > 1) {
    router.back()
    return
  }
  void router.push('/chat')
}
const userStore = useUserStore()
const chatStore = useChatStore()
const workflowRunsStore = useWorkflowRunsStore()
const editing = ref(false)
const avatarInput = ref<HTMLInputElement | null>(null)
const avatarSrc = ref('')
const avatarObjectUrl = ref('')
const avatarUploading = ref(false)
const activityMode = ref<ActivityMode>('daily')
const activityLoading = ref(false)
const remoteConversations = ref<Conversation[]>([])
const remoteRuns = ref<WorkflowRunSummary[]>([])
const activityModes: Array<{ id: ActivityMode; label: string }> = [{ id: 'daily', label: '每日' }, { id: 'weekly', label: '每周' }, { id: 'total', label: '累计' }]
const userInfo = ref({ username: '', email: '', avatar: '', createdAt: new Date() as Date | string })

const toDate = (value: string | number | Date | null | undefined): Date | null => {
  if (value == null || value === '') return null
  const date = value instanceof Date ? new Date(value.getTime()) : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}
const dayKey = (value: string | number | Date | null | undefined): string | null => {
  const date = toDate(value)
  return date ? date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0') : null
}
const addRecord = (records: ActivityRecord[], value: string | number | Date | null | undefined, tokens = 0) => {
  const date = dayKey(value)
  if (date) records.push({ date, events: 1, tokens: Number.isFinite(tokens) && tokens > 0 ? tokens : 0 })
}
const activityRecords = computed<ActivityRecord[]>(() => {
  const records: ActivityRecord[] = []
  remoteConversations.value.forEach(item => { addRecord(records, item.createdAt); if (item.updatedAt !== item.createdAt) addRecord(records, item.updatedAt) })
  remoteRuns.value.forEach(item => { addRecord(records, item.createdAt || item.startedAt); if (item.updatedAt && item.updatedAt !== item.createdAt) addRecord(records, item.updatedAt) })
  Object.values(workflowRunsStore.references).forEach(item => { addRecord(records, item.createdAt); if (item.updatedAt && item.updatedAt !== item.createdAt) addRecord(records, item.updatedAt) })
  chatStore.messages.forEach(item => {
    const tokens = Number(item.tokensUsed || 0) || Number(item.inputTokens || 0) + Number(item.reasoningTokens || 0) + Number(item.outputTokens || 0)
    addRecord(records, item.createdAt || item.timestamp, tokens)
  })
  return records
})
const activityMap = computed(() => {
  const map = new Map<string, { events: number; tokens: number }>()
  activityRecords.value.forEach(item => { const current = map.get(item.date) || { events: 0, tokens: 0 }; current.events += item.events; current.tokens += item.tokens; map.set(item.date, current) })
  return map
})
const today = computed(() => { const now = new Date(); return new Date(now.getFullYear(), now.getMonth(), now.getDate()) })
const formatDay = (date: Date) => date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
const activityTokenTotal = computed(() => activityRecords.value.reduce((sum, item) => sum + item.tokens, 0))
const formatCompactNumber = (value: number) => new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
const heatmapColumns = computed<ActivityColumn[]>(() => {
  const start = new Date(today.value)
  start.setDate(start.getDate() - 364 - start.getDay())
  const raw: Array<{ key: string; days: Array<{ key: string; date: Date; events: number; tokens: number }>; weekEvents: number; weekTokens: number }> = []
  for (let week = 0; week < 53; week += 1) {
    const days: Array<{ key: string; date: Date; events: number; tokens: number }> = []
    for (let day = 0; day < 7; day += 1) {
      const date = new Date(start); date.setDate(start.getDate() + week * 7 + day)
      const key = dayKey(date) || week + '-' + day
      days.push({ key, date, ...(activityMap.value.get(key) || { events: 0, tokens: 0 }) })
    }
    raw.push({ key: days[0].key, days, weekEvents: days.reduce((sum, item) => sum + item.events, 0), weekTokens: days.reduce((sum, item) => sum + item.tokens, 0) })
  }
  const scores = raw.flatMap(column => column.days.map(day => activityMode.value === 'weekly' ? column.weekTokens || column.weekEvents : day.tokens || day.events)).filter(Boolean)
  const maxScore = Math.max(...scores, 1)
  return raw.map(column => ({ key: column.key, days: column.days.map(day => {
    const metric = activityMap.value.get(day.key) || { events: 0, tokens: 0 }
    const score = activityMode.value === 'weekly' ? column.weekTokens || column.weekEvents : day.tokens || day.events
    const level = score ? Math.min(4, Math.max(1, Math.ceil((score / maxScore) * 4))) : 0
    const isFuture = day.date.getTime() > today.value.getTime()
    const quantity = activityMode.value === 'weekly' ? column.weekEvents : metric.events
    const tokenValue = activityMode.value === 'weekly' ? column.weekTokens : metric.tokens
    const tokenText = activityTokenTotal.value > 0 && tokenValue > 0 ? ' · ' + formatCompactNumber(tokenValue) + ' Token' : ''
    return { key: day.key, level: isFuture ? 0 : level, isToday: day.key === dayKey(today.value), isFuture, label: isFuture ? formatDay(day.date) + ' · 尚未到达' : formatDay(day.date) + ' · ' + quantity + ' 次活动' + tokenText }
  }) }))
})
const monthMarkers = computed(() => {
  const markers: Array<{ index: number; label: string }> = []
  heatmapColumns.value.forEach((column, index) => {
    const date = toDate(column.days[0].key)
    const previous = index ? toDate(heatmapColumns.value[index - 1].days[0].key) : null
    if (date && (!previous || date.getMonth() !== previous.getMonth())) markers.push({ index, label: date.getMonth() + 1 + '月' })
  })
  return markers
})
const activityDays = computed(() => Array.from(activityMap.value.values()).filter(item => item.events > 0).length)
const activityEventTotal = computed(() => activityRecords.value.reduce((sum, item) => sum + item.events, 0))
const activityTitle = computed(() => activityTokenTotal.value > 0 ? 'Token 活动' : '工作活动')
const activityCaption = computed(() => activityTokenTotal.value > 0 ? '按已观测的模型调用与本地运行记录聚合。' : '按已记录的对话与运行记录聚合，颜色代表活动密度。')
const activitySummary = computed(() => activityDays.value + ' 个活跃日 · ' + activityEventTotal.value + ' 次记录')
const dailyTokenPeak = computed(() => Math.max(0, ...Array.from(activityMap.value.values()).map(item => item.tokens)))
const streakMetrics = computed(() => {
  const activeDates = Array.from(activityMap.value.entries())
    .filter(([, item]) => item.events > 0)
    .map(([key]) => key)
    .sort()
  let longest = 0
  let run = 0
  let previous: Date | null = null
  activeDates.forEach(key => {
    const current = toDate(`${key}T00:00:00`)
    if (!current) return
    run = previous && Math.round((current.getTime() - previous.getTime()) / 86400000) === 1 ? run + 1 : 1
    longest = Math.max(longest, run)
    previous = current
  })
  let current = 0
  const cursor = new Date(today.value)
  while (activityMap.value.get(dayKey(cursor) || '')?.events) {
    current += 1
    cursor.setDate(cursor.getDate() - 1)
  }
  return { current, longest }
})
const longestChatDuration = computed(() => {
  const durations = remoteConversations.value.map(item => {
    const created = toDate(item.createdAt)?.getTime()
    const updated = toDate(item.updatedAt)?.getTime()
    return created && updated && updated >= created ? updated - created : 0
  })
  const longestMinutes = Math.floor(Math.max(0, ...durations) / 60000)
  if (!longestMinutes) return '—'
  if (longestMinutes < 60) return `${longestMinutes} 分`
  return `${Math.floor(longestMinutes / 60)} 小时 ${longestMinutes % 60} 分`
})
const profileStats = computed(() => [
  { label: '累计 Token 数', value: formatCompactNumber(activityTokenTotal.value) },
  { label: '峰值 Token 数', value: formatCompactNumber(dailyTokenPeak.value) },
  { label: '最长聊天时长', value: longestChatDuration.value },
  { label: '当前连续天数', value: `${streakMetrics.value.current} 天` },
  { label: '最长连续天数', value: `${streakMetrics.value.longest} 天` }
])
const roleBadge = computed(() => userInfo.value.username?.trim().toLowerCase() === 'admin' ? '管理员' : '成员')
const formatDate = (value: Date | string | undefined) => { const date = toDate(value); return date ? date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }) : '未知' }
const releaseAvatarObjectUrl = () => {
  if (avatarObjectUrl.value) {
    URL.revokeObjectURL(avatarObjectUrl.value)
    avatarObjectUrl.value = ''
  }
}
const loadAvatar = async (userId: string, avatarPath?: string) => {
  releaseAvatarObjectUrl()
  avatarSrc.value = ''
  if (!avatarPath) return
  try {
    const blob = await userApi.getAvatar(userId)
    avatarObjectUrl.value = URL.createObjectURL(blob)
    avatarSrc.value = avatarObjectUrl.value
  } catch (error) {
    console.warn('头像读取失败', error)
  }
}
const openAvatarPicker = () => avatarInput.value?.click()
const handleAvatarChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const supportedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif']
  if (!supportedTypes.includes(file.type)) return ElMessage.warning('请选择 JPG、PNG、WebP 或 GIF 图片')
  if (file.size > 5 * 1024 * 1024) return ElMessage.warning('头像图片不能超过 5MB')
  const userId = userStore.currentUser?.id
  if (!userId) return ElMessage.error('本机身份尚未就绪，请稍后重试')

  avatarUploading.value = true
  try {
    const updatedUser = await userApi.uploadAvatar(userId, file)
    const avatar = updatedUser.avatar || userStore.currentUser?.avatar || ''
    userStore.setCurrentUser({
      id: updatedUser.id || userId,
      username: updatedUser.username || userInfo.value.username,
      email: updatedUser.email || userInfo.value.email,
      avatar,
      createdAt: updatedUser.createdAt || userStore.currentUser?.createdAt
    })
    userInfo.value.avatar = avatar
    await loadAvatar(userId, avatar)
    ElMessage.success('头像上传成功')
  } catch (error: any) {
    ElMessage.error('头像上传失败：' + (error?.response?.data?.message || error?.message || '请稍后重试'))
  } finally {
    avatarUploading.value = false
  }
}
const inviteFriend = () => ElMessage.info('邀请功能即将开放')
const shareProfile = async () => {
  const profileText = `${userInfo.value.username || '用户'} · ${userInfo.value.email || 'Kinlin AI'}`
  try {
    await navigator.clipboard.writeText(profileText)
    ElMessage.success('个人资料已复制')
  } catch {
    ElMessage.warning('当前环境不支持复制，请手动分享')
  }
}
const updateProfile = async () => {
  if (!userInfo.value.email) return ElMessage.warning('请输入邮箱地址')
  if (!userStore.currentUser?.id) return ElMessage.error('本机身份尚未就绪，请稍后重试')
  try {
    await userApi.updateUser(userStore.currentUser.id, { username: userInfo.value.username, email: userInfo.value.email })
    await userStore.loadCurrentUser({ force: true }); editing.value = false; ElMessage.success('个人信息已更新')
  } catch (error: any) { ElMessage.error('更新失败: ' + (error.message || '未知错误')) }
}
const loadActivity = async () => {
  activityLoading.value = true
  const [conversations, runs] = await Promise.allSettled([conversationApi.getUserConversations(), workflowApi.listRuns({ summary: true, page: 1, pageSize: 100 })])
  if (conversations.status === 'fulfilled') remoteConversations.value = conversations.value || []
  if (runs.status === 'fulfilled') remoteRuns.value = runs.value.items || []
  activityLoading.value = false
}
onMounted(async () => {
  await userStore.loadCurrentUser()
  if (userStore.currentUser) {
    userInfo.value = { username: userStore.currentUser.username || '', email: userStore.currentUser.email || '', avatar: userStore.currentUser.avatar || '', createdAt: userStore.currentUser.createdAt || new Date() }
    await loadAvatar(userStore.currentUser.id, userStore.currentUser.avatar)
  }
  void loadActivity()
})
onBeforeUnmount(releaseAvatarObjectUrl)
</script>

<style scoped lang="scss">
.user-view { width: 100%; height: 100%; min-height: 0; overflow: hidden; background: var(--bg-app); color: var(--text-primary); }
.user-content { width: min(100%, 1400px); height: 100%; min-width: 0; min-height: 0; margin: 0 auto; padding: 30px clamp(20px, 4vw, 58px) 52px; display: flex; flex-direction: column; gap: 20px; overflow-y: auto; overflow-x: hidden; }
.content-header { padding-bottom: 21px; display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; border-bottom: 1px solid var(--border-light); }
.back-to-app { min-height: 30px; margin: 0 0 12px; padding: 0; display: inline-flex; align-items: center; gap: 6px; border: 0; color: var(--text-secondary); background: transparent; font: inherit; font-size: 12px; cursor: pointer; }
.back-to-app:hover, .back-to-app:focus-visible { color: var(--text-primary); }.back-to-app:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; }
.content-eyebrow, .card-kicker { display: block; color: var(--primary-color); font: 600 10px/1 var(--font-mono, monospace); letter-spacing: .12em; }
.content-eyebrow { margin-bottom: 6px; } .content-header h1 { margin: 0; color: var(--text-primary); font: 650 clamp(24px, 2.4vw, 32px)/1.15 var(--font-serif); letter-spacing: -.025em; } .content-header p { margin: 7px 0 0; color: var(--text-secondary); font-size: 12px; }
.content-actions { display: flex; align-items: center; gap: 8px; } .profile-action, .activity-mode { border: 0; color: var(--text-secondary); background: transparent; font: inherit; cursor: pointer; transition: var(--transition); } .profile-action { min-height: 33px; padding: 0 4px; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; } .profile-action:hover, .profile-action:focus-visible { color: var(--text-primary); } .profile-action:focus-visible, .avatar-uploader:focus-visible, .activity-mode:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; } .profile-status { color: var(--text-muted); cursor: default; }
.user-sections { display: flex; align-items: center; gap: 4px; padding-bottom: 4px; border-bottom: 1px solid var(--border-light); }
.user-sections button { min-height: 34px; padding: 0 12px; border: 0; border-radius: 6px; color: var(--text-muted); background: transparent; font: inherit; font-size: 12px; cursor: pointer; transition: var(--transition); }
.user-sections button:hover, .user-sections button.active { color: var(--text-primary); background: var(--primary-fade); }
.user-sections button.active { box-shadow: inset 0 -2px var(--primary-color); }
.identity-hero, .security-hero { padding: 12px 0 2px; display: grid; justify-items: center; gap: 7px; text-align: center; } .avatar-uploader { padding: 0; border: 0; cursor: pointer; border-radius: 50%; background: transparent; } .avatar-uploader:disabled { cursor: wait; opacity: .72; } .avatar-input { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; clip-path: inset(50%); } .avatar-hint { margin: -1px 0 0; color: var(--text-muted); font-size: 10px; } .hero-avatar { position: relative; width: 92px; height: 92px; display: grid; place-items: center; overflow: visible; color: var(--primary-color); background: var(--primary-fade); border: 1px solid color-mix(in srgb, var(--primary-color) 26%, var(--border-light)); border-radius: 50%; transition: var(--transition); } .hero-avatar img { width: 100%; height: 100%; object-fit: cover; border-radius: inherit; } .avatar-uploader:hover .hero-avatar { border-color: var(--primary-color); transform: translateY(-1px); } .avatar-edit { position: absolute; right: 0; bottom: 2px; width: 24px; height: 24px; display: grid; place-items: center; color: #fff; background: var(--primary-color); border: 3px solid var(--bg-app); border-radius: 50%; } .hero-name { margin: 6px 0 0; color: var(--text-primary); font: 650 28px/1.1 var(--font-serif); letter-spacing: -.025em; } .hero-handle { margin: 0; display: flex; align-items: center; gap: 9px; color: var(--text-secondary); font-size: 12px; } .hero-badge { height: 22px; padding: 0 9px; display: inline-flex; align-items: center; border: 1px solid var(--primary-line); border-radius: 999px; color: var(--primary-color); background: var(--primary-fade); font-size: 10px; font-weight: 600; }
.stats-row { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); overflow: hidden; border: 1px solid var(--border-light); border-radius: 14px; background: color-mix(in srgb, var(--surface-solid) 92%, transparent); } .stats-cell { min-height: 80px; padding: 15px 12px; display: grid; align-content: center; justify-items: center; gap: 4px; border-right: 1px solid var(--border-light); } .stats-cell:hover { background: var(--bg-input); } .stats-cell:last-child { border-right: 0; } .stats-cell strong { color: var(--text-primary); font: 700 21px/1.1 var(--font-sans); } .stats-cell span { color: var(--text-secondary); font-size: 11px; }
.activity-card, .detail-card, .security-panel { border: 1px solid var(--border-light); border-radius: 14px; background: color-mix(in srgb, var(--surface-solid) 92%, transparent); } .activity-card { padding: 20px 22px 14px; } .activity-card__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; } .activity-card__header h2 { margin: 7px 0 0; color: var(--text-primary); font: 650 17px/1.2 var(--font-sans); } .activity-card__header p { margin: 5px 0 0; color: var(--text-secondary); font-size: 11px; } .activity-modes { display: inline-flex; gap: 2px; flex-shrink: 0; } .activity-mode { position: relative; padding: 4px 6px 7px; border-color: transparent; border-radius: 5px; font-size: 12px; } .activity-mode.active { color: var(--text-primary); } .activity-mode.active::after { content: ''; position: absolute; right: 6px; bottom: 2px; left: 6px; height: 2px; border-radius: 2px; background: var(--primary-color); }
.activity-chart { margin-top: 20px; overflow-x: auto; } .activity-chart.loading { opacity: .72; } .activity-months, .activity-grid-shell, .activity-legend { min-width: 700px; } .activity-months { margin-left: 31px; display: grid; grid-template-columns: repeat(53, minmax(8px, 1fr)); column-gap: 4px; min-height: 17px; color: var(--text-muted); font-size: 10px; } .activity-months span { white-space: nowrap; } .activity-grid-shell { display: grid; grid-template-columns: 23px minmax(0, 1fr); gap: 8px; } .weekday-labels { display: grid; grid-template-rows: repeat(7, 12px); row-gap: 4px; color: var(--text-muted); font-size: 9px; line-height: 12px; } .weekday-labels span:nth-child(1) { grid-row: 2; } .weekday-labels span:nth-child(2) { grid-row: 4; } .weekday-labels span:nth-child(3) { grid-row: 6; }
.heatmap-grid { display: grid; grid-template-columns: repeat(53, minmax(8px, 1fr)); gap: 4px; } .heatmap-week { display: grid; grid-template-rows: repeat(7, 12px); gap: 4px; } .heatmap-cell { width: 100%; min-width: 0; height: 12px; padding: 0; border: 1px solid transparent; border-radius: 3px; background: color-mix(in srgb, var(--text-primary) 5%, var(--bg-input)); transition: var(--transition); } button.heatmap-cell { cursor: pointer; } button.heatmap-cell:hover, button.heatmap-cell:focus-visible { z-index: 1; border-color: var(--primary-color); transform: scale(1.18); outline: 0; } .heatmap-cell.level-1 { background: color-mix(in srgb, var(--primary-color) 22%, var(--bg-input)); } .heatmap-cell.level-2 { background: color-mix(in srgb, var(--primary-color) 40%, var(--bg-input)); } .heatmap-cell.level-3 { background: color-mix(in srgb, var(--primary-color) 62%, var(--bg-input)); } .heatmap-cell.level-4 { background: color-mix(in srgb, var(--primary-color) 86%, #fff); } .heatmap-cell.today { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary-color) 72%, #fff); } .heatmap-cell.future { opacity: .42; }
.activity-legend { margin-top: 14px; display: flex; align-items: center; justify-content: flex-end; gap: 6px; color: var(--text-muted); font-size: 10px; } .legend-swatches { display: inline-flex; gap: 4px; } .legend-swatches .heatmap-cell { width: 12px; flex: 0 0 12px; } .activity-card__footer { margin-top: 14px; padding-top: 11px; display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid color-mix(in srgb, var(--border-light) 72%, transparent); color: var(--text-muted); font-size: 10px; }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; align-items: start; } .detail-card { overflow: hidden; } .detail-card__header { min-height: 58px; padding: 14px 18px; border-bottom: 1px solid var(--border-light); } .card-kicker { margin-bottom: 5px; font-size: 9px; } .detail-card__header h3 { margin: 0; color: var(--text-primary); font-size: 15px; } .insight-list { margin: 0; padding: 6px 18px 12px; } .insight-row { min-height: 42px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid color-mix(in srgb, var(--border-light) 60%, transparent); } .insight-row:last-child { border-bottom: 0; } .insight-row dt { color: var(--text-secondary); font-size: 12px; } .insight-row dd { max-width: 70%; margin: 0; overflow: hidden; color: var(--text-primary); font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; } .detail-card__body { padding: 16px 18px 18px; }
.user-form .el-form-item { margin-bottom: 15px; } .user-form .el-form-item:last-child { margin-bottom: 0; } .user-form :deep(.el-form-item__label) { margin-bottom: 6px; padding: 0; color: var(--text-primary); font-size: 12px; font-weight: 650; } .custom-input :deep(.el-input__wrapper) { min-height: 38px; border: 1px solid var(--border-light); border-radius: 9px; background: var(--bg-input); box-shadow: none; } .custom-input :deep(.el-input__inner) { color: var(--text-primary); font-size: 12px; } .custom-input :deep(.el-input__wrapper:hover) { border-color: var(--border-hover); } .form-hint { margin-top: 5px; color: var(--text-disabled); font-size: 11px; } .user-form :deep(.el-button) { min-width: 108px; height: 34px; border-radius: 9px; font-size: 12px; font-weight: 650; } .user-form :deep(.el-button--primary) { border-color: var(--primary-color); background: var(--primary-color); } .user-form :deep(.el-button.is-disabled) { color: var(--text-disabled); background: var(--bg-input); border-color: var(--border-light); }
.security-panel { width: min(100%, 560px); margin: 10px auto 0; padding: 20px 22px 22px; } .security-hero .hero-name { font-size: 23px; }
@media (max-width: 900px) { .detail-grid { grid-template-columns: 1fr; } .stats-row { grid-template-columns: repeat(3, minmax(0, 1fr)); } .stats-cell:nth-child(3) { border-right: 0; } .stats-cell:nth-child(-n + 3) { border-bottom: 1px solid var(--border-light); } }
@media (max-width: 640px) { .user-content { padding: 22px 14px 38px; } .content-header { flex-direction: column; } .content-actions { width: 100%; flex-wrap: wrap; } .profile-status { margin-left: auto; } .stats-row { grid-template-columns: repeat(2, minmax(0, 1fr)); } .stats-cell:nth-child(2n) { border-right: 0; } .stats-cell:nth-child(n + 3) { border-top: 1px solid var(--border-light); } .activity-card { padding: 18px 14px 13px; } .activity-card__header { flex-direction: column; gap: 10px; } .activity-card__footer { flex-direction: column; gap: 4px; } }

/* Keep the calendar rhythm compact instead of stretching cells across the card. */
.activity-months,
.activity-grid-shell,
.activity-legend {
  width: 875px;
  min-width: 875px;
  margin-inline: auto;
  box-sizing: border-box;
}

.activity-months {
  padding-left: 31px;
  margin-left: auto;
  grid-template-columns: repeat(53, 12px);
  column-gap: 4px;
}

.activity-grid-shell {
  grid-template-columns: 23px 844px;
}

.heatmap-grid {
  width: 844px;
  grid-template-columns: repeat(53, 12px);
  gap: 4px;
}

.heatmap-cell {
  width: 12px;
  height: 12px;
  border-radius: 4px;
}

.activity-legend {
  justify-content: flex-end;
}
</style>
