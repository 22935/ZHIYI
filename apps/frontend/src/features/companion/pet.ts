/**
 * Companion 养成核心：纯函数 + 可注入时钟/随机数。
 *
 * 边界：这里的所有数值都是「本地展示层状态」，只写 localStorage，
 * 不进入任何后端 Store，不参与任务执行，也不改变进度投影的真相。
 * UI 与桌面托盘都只读它的派生结果。
 */
import type { CompanionState } from './types'

export type PetAction = 'pat' | 'feed' | 'play' | 'chat' | 'progress' | 'task' | 'visit'
export type PetMood = 'curious' | 'content' | 'sleepy' | 'excited' | 'concerned'

export interface PetProfile {
  version: 1
  affinity: number
  energy: number
  totalPats: number
  totalChats: number
  totalProgressQueries: number
  totalTaskCards: number
  totalFeeds: number
  totalPlays: number
  streakDays: number
  lastActiveDate: string
  lastPatAt: number
  lastFeedAt: number
  lastPlayAt: number
  lastInteractionAt: number
  createdAt: number
  achievements: string[]
}

export interface Achievement {
  id: string
  label: string
  description: string
}

export interface PetActionResult {
  profile: PetProfile
  message: string
  tone: 'normal' | 'cooldown'
  unlocked: Achievement[]
  gained: number
  /** 互动希望呈现的语义状态；null 表示不改形象。告警态由 UI 决定不打断。 */
  state: CompanionState | null
}

export const LEVEL_STEP = 60
export const MAX_LEVEL = 12
export const PET_STORAGE_KEY = 'companion.pet.v1'
export const PAT_COOLDOWN_MS = 1500
export const FEED_COOLDOWN_MS = 5 * 60_000
export const PLAY_COOLDOWN_MS = 90_000
export const ENERGY_DECAY_PER_HOUR = 3
export const AFFINITY_DECAY_PER_DAY = 4
export const MAX_AWAY_DAYS = 7

export const TITLES = [
  '初来乍到', '见习伙伴', '工位常客', '进度小助手',
  '知心搭档', '默契同行', '老练管家', '心有灵犀',
  '工位守护者', '金牌搭档', '知宝大人', '传说中的知宝'
] as const

export const MOOD_LABEL: Record<PetMood, string> = {
  curious: '好奇',
  content: '安心',
  sleepy: '困困的',
  excited: '元气满满',
  concerned: '有点担心'
}

export const ACHIEVEMENTS: Achievement[] = [
  { id: 'first_meet', label: '初次见面', description: '第一次唤起知宝' },
  { id: 'chatty', label: '话匣子', description: '累计聊天 10 次' },
  { id: 'headpat_30', label: '摸摸达人', description: '摸头 30 次' },
  { id: 'streak_3', label: '连续三天', description: '连续 3 天来看它' },
  { id: 'night_owl', label: '夜猫子', description: '在深夜和知宝互动' },
  { id: 'level_5', label: '渐入佳境', description: '亲密度达到 5 级' },
  { id: 'watcher', label: '进度观察员', description: '查询进度 10 次' },
  { id: 'planner', label: '小小规划师', description: '整理 3 张任务卡' }
]

const LINES: Record<PetAction, string[]> = {
  pat: ['被摸到头啦，今天也一起慢慢来。', '嗯嗯，我在呢。', '这一下很舒服，好感度悄悄涨了一点。'],
  feed: ['吃点心时间！谢谢你记得我。', '吃饱了才有力气帮你看进度。', '好甜，分你一半。'],
  play: ['再玩一小会儿，进度我替你盯着。', '接住啦！', '动一动，脑袋也清醒了一点。'],
  chat: ['和你聊天挺开心的。', '嗯嗯，我记下了。', '想说什么都可以，我不着急。'],
  progress: ['帮你盯着呢，有变化我会说。', '进度我去看了，详细正文还是留给工作台。', '查询完毕，安心。'],
  task: ['先记成任务卡，确认权在你手上。', '我不会替你点开始的，放心。', '想做的事又多了一件。'],
  visit: ['你来啦，我先待在角落。', '今天也在，随时叫我。', '工位还是老样子，真好。']
}

const COOLDOWN_LINES: Record<'pat' | 'feed' | 'play', string> = {
  pat: '摸得太快啦，让我缓一下。',
  feed: '刚吃过，再吃会撑到的。',
  play: '先歇一会儿，等下再玩。'
}

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value))

/** 本地日期键：用本地日历日，不用 UTC，避免国内用户在清晨被算成「昨天」。 */
export function localDateKey(now: number): string {
  const date = new Date(now)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

export function previousDateKey(key: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key)
  if (!match) return ''
  const stamp = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) - 86_400_000
  return new Date(stamp).toISOString().slice(0, 10)
}

export function createPetProfile(now: number): PetProfile {
  return {
    version: 1,
    affinity: 0,
    energy: 80,
    totalPats: 0,
    totalChats: 0,
    totalProgressQueries: 0,
    totalTaskCards: 0,
    totalFeeds: 0,
    totalPlays: 0,
    streakDays: 0,
    lastActiveDate: '',
    // 0 = 从未发生。now 一律为 epoch 毫秒，因此 now - 0 必然大于任何冷却窗口；
    // 不用 -Infinity 是因为 JSON.stringify 会把它写成 null，来回存取会丢语义。
    lastPatAt: 0,
    lastFeedAt: 0,
    lastPlayAt: 0,
    lastInteractionAt: now,
    createdAt: now,
    achievements: []
  }
}

const finiteOr = (value: unknown, fallback: number): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback

/** localStorage 是用户可编辑的，任何字段都可能是错的；一律收敛成合法档案。 */
export function sanitizePetProfile(raw: unknown, now: number): PetProfile {
  const base = createPetProfile(now)
  if (!raw || typeof raw !== 'object') return base
  const data = raw as Record<string, unknown>
  const known = new Set(ACHIEVEMENTS.map(item => item.id))
  const achievements = Array.isArray(data.achievements)
    ? [...new Set(data.achievements.filter((id): id is string => typeof id === 'string' && known.has(id)))]
    : []
  return {
    version: 1,
    affinity: clamp(Math.floor(finiteOr(data.affinity, 0)), 0, LEVEL_STEP * MAX_LEVEL),
    energy: clamp(Math.floor(finiteOr(data.energy, base.energy)), 0, 100),
    totalPats: clamp(Math.floor(finiteOr(data.totalPats, 0)), 0, 1e9),
    totalChats: clamp(Math.floor(finiteOr(data.totalChats, 0)), 0, 1e9),
    totalProgressQueries: clamp(Math.floor(finiteOr(data.totalProgressQueries, 0)), 0, 1e9),
    totalTaskCards: clamp(Math.floor(finiteOr(data.totalTaskCards, 0)), 0, 1e9),
    totalFeeds: clamp(Math.floor(finiteOr(data.totalFeeds, 0)), 0, 1e9),
    totalPlays: clamp(Math.floor(finiteOr(data.totalPlays, 0)), 0, 1e9),
    streakDays: clamp(Math.floor(finiteOr(data.streakDays, 0)), 0, 36500),
    lastActiveDate: typeof data.lastActiveDate === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(data.lastActiveDate)
      ? data.lastActiveDate : '',
    lastPatAt: finiteOr(data.lastPatAt, base.lastPatAt),
    lastFeedAt: finiteOr(data.lastFeedAt, base.lastFeedAt),
    lastPlayAt: finiteOr(data.lastPlayAt, base.lastPlayAt),
    lastInteractionAt: finiteOr(data.lastInteractionAt, now),
    createdAt: finiteOr(data.createdAt, now),
    achievements
  }
}

export function levelOf(affinity: number): number {
  return clamp(1 + Math.floor(Math.max(0, affinity) / LEVEL_STEP), 1, MAX_LEVEL)
}

export function levelProgress(affinity: number): number {
  const level = levelOf(affinity)
  if (level >= MAX_LEVEL) return 1
  return (Math.max(0, affinity) % LEVEL_STEP) / LEVEL_STEP
}

export function titleOf(level: number): string {
  return TITLES[clamp(level, 1, MAX_LEVEL) - 1]
}

/** 离开越久，精力缓慢回落；好感度只在两天以上缺席时轻微衰减，且不惩罚短期离开。 */
export function applyTimeDecay(profile: PetProfile, now: number): PetProfile {
  const awayMs = Math.max(0, now - profile.lastInteractionAt)
  const hours = awayMs / 3_600_000
  const days = awayMs / 86_400_000
  const energyLoss = Math.floor(hours * ENERGY_DECAY_PER_HOUR)
  const affinityLoss = days > 2 ? Math.floor(Math.min(days - 2, MAX_AWAY_DAYS) * AFFINITY_DECAY_PER_DAY) : 0
  if (energyLoss === 0 && affinityLoss === 0) return profile
  return {
    ...profile,
    energy: clamp(profile.energy - energyLoss, 0, 100),
    affinity: clamp(profile.affinity - affinityLoss, 0, LEVEL_STEP * MAX_LEVEL)
  }
}

export function moodOf(
  profile: PetProfile,
  now: number,
  state: CompanionState = 'idle'
): PetMood {
  if (state === 'error' || state === 'alert') return 'concerned'
  const hour = new Date(now).getHours()
  if (profile.energy < 25 || hour >= 23 || hour < 6) return 'sleepy'
  if (profile.energy > 75 && now - profile.lastInteractionAt < 60_000) return 'excited'
  if (profile.totalChats + profile.totalPats === 0) return 'curious'
  return 'content'
}

interface AchievementCondition {
  id: string
  holds(profile: PetProfile, now: number): boolean
}

const CONDITIONS: AchievementCondition[] = [
  { id: 'first_meet', holds: () => true },
  { id: 'chatty', holds: p => p.totalChats >= 10 },
  { id: 'headpat_30', holds: p => p.totalPats >= 30 },
  { id: 'streak_3', holds: p => p.streakDays >= 3 },
  { id: 'night_owl', holds: (_p, now) => { const h = new Date(now).getHours(); return h >= 23 || h < 6 } },
  { id: 'level_5', holds: p => levelOf(p.affinity) >= 5 },
  { id: 'watcher', holds: p => p.totalProgressQueries >= 10 },
  { id: 'planner', holds: p => p.totalTaskCards >= 3 }
]

function unlockAchievements(profile: PetProfile, now: number): { profile: PetProfile; unlocked: Achievement[] } {
  const owned = new Set(profile.achievements)
  const unlocked = ACHIEVEMENTS.filter(item =>
    !owned.has(item.id) && CONDITIONS.find(rule => rule.id === item.id)?.holds(profile, now)
  )
  if (!unlocked.length) return { profile, unlocked: [] }
  return {
    profile: { ...profile, achievements: [...profile.achievements, ...unlocked.map(item => item.id)] },
    unlocked
  }
}

function pick(lines: string[], rng: () => number): string {
  if (!lines.length) return ''
  const index = Math.min(lines.length - 1, Math.max(0, Math.floor(rng() * lines.length)))
  return lines[index]
}

/**
 * 唯一的状态变更入口。冷却只挡「刷数值」，不挡交互本身：
 * 用户依然能收到一句俏皮话，好感度不会因连点暴涨。
 */
export function applyPetAction(
  input: PetProfile,
  action: PetAction,
  now: number,
  rng: () => number = Math.random
): PetActionResult {
  let profile = applyTimeDecay(input, now)
  let gained = 0
  let state: CompanionState | null = null
  let tone: PetActionResult['tone'] = 'normal'
  let message = pick(LINES[action], rng)

  const today = localDateKey(now)
  if (profile.lastActiveDate !== today) {
    profile = {
      ...profile,
      streakDays: profile.lastActiveDate === previousDateKey(today) ? profile.streakDays + 1 : 1,
      lastActiveDate: today
    }
  }

  switch (action) {
    case 'pat': {
      const cooled = now - profile.lastPatAt < PAT_COOLDOWN_MS
      tone = cooled ? 'cooldown' : 'normal'
      message = cooled ? COOLDOWN_LINES.pat : message
      profile = { ...profile, totalPats: profile.totalPats + 1, lastPatAt: now }
      gained = cooled ? 0 : 1
      state = 'happy'
      break
    }
    case 'feed': {
      const cooled = now - profile.lastFeedAt < FEED_COOLDOWN_MS
      tone = cooled ? 'cooldown' : 'normal'
      message = cooled ? COOLDOWN_LINES.feed : message
      profile = { ...profile, totalFeeds: profile.totalFeeds + 1, lastFeedAt: now }
      gained = cooled ? 0 : 4
      if (!cooled) profile = { ...profile, energy: clamp(profile.energy + 18, 0, 100) }
      state = 'happy'
      break
    }
    case 'play': {
      const cooled = now - profile.lastPlayAt < PLAY_COOLDOWN_MS
      tone = cooled ? 'cooldown' : 'normal'
      message = cooled ? COOLDOWN_LINES.play : message
      profile = { ...profile, totalPlays: profile.totalPlays + 1, lastPlayAt: now }
      gained = cooled ? 0 : 5
      if (!cooled) profile = { ...profile, energy: clamp(profile.energy - 12, 0, 100) }
      state = 'happy'
      break
    }
    case 'chat':
      profile = { ...profile, totalChats: profile.totalChats + 1 }
      gained = 2
      break
    case 'progress':
      profile = { ...profile, totalProgressQueries: profile.totalProgressQueries + 1 }
      gained = 1
      break
    case 'task':
      profile = { ...profile, totalTaskCards: profile.totalTaskCards + 1 }
      gained = 2
      break
    case 'visit':
      gained = 1
      break
  }

  profile = { ...profile, affinity: clamp(profile.affinity + gained, 0, LEVEL_STEP * MAX_LEVEL), lastInteractionAt: now }
  const result = unlockAchievements(profile, now)
  return {
    profile: result.profile,
    message: gained > 0 ? `${message}（+${gained} 好感）` : message,
    tone,
    unlocked: result.unlocked,
    gained,
    state
  }
}

export interface PetStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export function loadPetProfile(storage: PetStorage | null, now: number): PetProfile {
  if (!storage) return createPetProfile(now)
  try {
    const raw = storage.getItem(PET_STORAGE_KEY)
    return raw ? sanitizePetProfile(JSON.parse(raw), now) : createPetProfile(now)
  } catch {
    return createPetProfile(now)
  }
}

export function savePetProfile(storage: PetStorage | null, profile: PetProfile): void {
  if (!storage) return
  try {
    storage.setItem(PET_STORAGE_KEY, JSON.stringify(profile))
  } catch {
    // 隐私模式或配额耗尽：养成状态退化为内存态，不影响主流程。
  }
}
