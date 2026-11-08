/**
 * 语音控制指令：把口语化说法翻译成 Companion 面板动作。
 *
 * 与 intent.ts 的分工：intent 负责「问进度 / 记任务 / 闲聊 / 陪伴」这类
 * 对话场景；这里只负责「收起、安静、换形象、别说了、摸摸头」这类
 * 对界面本身的控制。先匹配命令再走对话，避免「把面板收起来」被当成闲聊。
 */
export type CompanionCommand =
  | 'collapse'
  | 'summon'
  | 'quiet-on'
  | 'quiet-off'
  | 'mute-on'
  | 'mute-off'
  | 'stop-speaking'
  | 'reset-position'
  | 'open-customizer'
  | 'close-customizer'
  | 'next-skin'
  | 'interact-pat'
  | 'interact-feed'
  | 'interact-play'

export interface CommandMatch {
  id: CompanionCommand
  reply: string
}

interface CommandRule {
  id: CompanionCommand
  reply: string
  pattern: RegExp
}

/** 顺序即优先级：「别说了」要早于「别打扰」，「关掉免打扰」要早于「安静」。 */
const RULES: CommandRule[] = [
  {
    id: 'stop-speaking',
    reply: '好，我不说啦。',
    pattern: /(别说了|不要说了|住口|闭嘴|停下|停一下|安静点|别念了)/i
  },
  {
    id: 'quiet-off',
    reply: '好，我回来啦，有事随时叫我。',
    pattern: /(取消免打扰|关掉免打扰|别免打扰|不用安静|可以说话了|回来吧|活跃一点)/i
  },
  {
    id: 'mute-off',
    reply: '声音打开啦。',
    pattern: /(打开声音|开启声音|取消静音|关掉静音|出声吧|说话吧)/i
  },
  {
    id: 'mute-on',
    reply: '好，我只用气泡和文字回答你。',
    pattern: /(关掉声音|关闭声音|静音|别出声|不要出声|小声点|闭麦)/i
  },
  {
    id: 'quiet-on',
    reply: '好，我先安静待着，不主动搭话了。',
    pattern: /(免打扰|安静一会|安静一点|别打扰|不要打扰|别吵|先别理我|自己待着)/i
  },
  {
    id: 'collapse',
    reply: '好，我先退到角落，点一下就能叫我回来。',
    pattern: /(收起|藏起来|躲起来|退下|下去|缩小|关掉面板|关闭面板|不见了)/i
  },
  {
    id: 'summon',
    reply: '我在，叫我做什么？',
    pattern: /(出来|过来|展开|打开面板|现身|醒醒|在吗知宝)/i
  },
  {
    id: 'reset-position',
    reply: '回到老位置啦。',
    pattern: /(回到右下角|回原位|归位|回到角落|重置位置)/i
  },
  {
    id: 'open-customizer',
    reply: '打开形象工坊啦，颜色、形状和图片都能自己改。',
    pattern: /(自定义|自己设计|形象工坊|DIY|换外观|改名字|设计形象|捏一个)/i
  },
  {
    id: 'close-customizer',
    reply: '先收起工坊，随时可以再打开。',
    pattern: /(关掉工坊|关闭工坊|收起工坊|退出自定义)/i
  },
  {
    id: 'next-skin',
    reply: '换好啦，看看这个样子喜欢吗？',
    pattern: /(换个形象|换形象|换皮肤|切换皮肤|换个样子|换一个样子|下一个皮肤)/i
  },
  {
    id: 'interact-pat',
    reply: '被摸到头啦，嘿嘿。',
    pattern: /(摸摸头|摸一下|摸摸|拍拍头)/i
  },
  {
    id: 'interact-feed',
    reply: '吃点心时间！谢谢你记得我。',
    pattern: /(喂点心|喂我|给点吃的|吃点东西|喂饭)/i
  },
  {
    id: 'interact-play',
    reply: '再玩一小会儿，进度我替你盯着。',
    pattern: /(玩一会|玩一下|陪我玩|来玩|玩个游戏)/i
  }
]

export function matchCompanionCommand(text: string): CommandMatch | null {
  const value = text.trim()
  if (!value) return null
  const rule = RULES.find(item => item.pattern.test(value))
  return rule ? { id: rule.id, reply: rule.reply } : null
}

export const COMMAND_IDS: CompanionCommand[] = RULES.map(rule => rule.id)
