import { beforeEach, describe, expect, it } from 'vitest'
import { clearConversationLaunchIdentity, conversationLaunchRequestId } from './conversationLaunchIdentity'

describe('Legacy Conversation identity safety', () => {
  beforeEach(() => { sessionStorage.clear(); localStorage.clear(); localStorage.setItem('userId', 'test-local-owner') })
  it('reads existing legacy identity hints without clearing or replacing unknown submissions', () => {
    sessionStorage.setItem('chat.workflow_submission.conversation', JSON.stringify({ conversationId: 'conversation', text: '目标', clientRequestId: 'legacy' }))
    sessionStorage.setItem('unrelated', 'preserve')
    expect(conversationLaunchRequestId(sessionStorage, 'conversation', '目标')).toBe('legacy')
    expect(() => clearConversationLaunchIdentity(sessionStorage, 'conversation')).toThrow('未确认的操作身份不能清理')
    expect(() => conversationLaunchRequestId(sessionStorage, 'conversation', 'new intent')).toThrow()
    expect(sessionStorage.getItem('unrelated')).toBe('preserve')
    expect(JSON.parse(sessionStorage.getItem('chat.workflow_submission.conversation')!).clientRequestId).toBe('legacy')
  })
  it('does not generate a second identity outside the command authority', () => {
    localStorage.removeItem('userId')
    expect(() => conversationLaunchRequestId(sessionStorage, 'new-conversation', '目标')).toThrow('本机身份尚未就绪')
    expect(sessionStorage.length).toBe(0)
  })
})
