/** Token content counts are exact only with a matching configured tokenizer.
 * Wire framing, tools and images use explicit conservative allowances. DSH's
 * chars/4 estimator is audited but intentionally not treated as exact admission.
 */
import { readFile } from 'node:fs/promises'
import type { Message } from './contracts.ts'

export function wire(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(wire).join(',') + ']'
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + wire((value as any)[key])).join(',') + '}'
  const encoded = JSON.stringify(value)
  if (encoded === undefined || (typeof value === 'number' && !Number.isFinite(value))) throw new TypeError('Non-JSON input')
  return encoded
}
export class TokenMeter {
  fallbackUsed = false
  readonly method: string
  private encoder?: (text: string) => number
  constructor(encoder?: (text: string) => number, method = 'utf8-upper-bound') {
    this.encoder = encoder; this.method = method
  }
  text(text: string): number {
    if (this.encoder) {
      try {
        const count = this.encoder(text)
        if (!Number.isSafeInteger(count) || count < 0) throw new TypeError('Invalid token count')
        return count
      } catch { this.fallbackUsed = true }
    }
    return Buffer.byteLength(text, 'utf8')
  }
  value(value: unknown): number { return this.text(wire(value)) }
  message(message: Message): number {
    const images = (value: any): number => {
      if (Array.isArray(value)) return value.reduce((n, v) => n + images(v), 0)
      if (value && typeof value === 'object') return Number(['input_image', 'image_url', 'image'].includes(value.type)) + Object.values(value).reduce<number>((n, v) => n + images(v), 0)
      return 0
    }
    return this.value(message) + 24 + images(message) * 8192
  }
  messages(messages: Message[]): number { return messages.reduce((n, m) => n + this.message(m), 0) }
  fixed(instructions: string, tools: unknown[]): number { return this.text(instructions) + (tools.length ? this.value(tools) : 0) + 64 }
}

export async function modelMeter(model: string, tokenizer?: { json: string; config: string }): Promise<TokenMeter> {
  if (tokenizer) {
    // Local, model-specific assets only. No implicit Hub download or network.
    try {
      const { Tokenizer } = await import('@huggingface/tokenizers')
      const [json, config] = await Promise.all([readFile(tokenizer.json, 'utf8'), readFile(tokenizer.config, 'utf8')])
      const instance = new Tokenizer(JSON.parse(json), JSON.parse(config))
      return new TokenMeter(text => instance.encode(text, { add_special_tokens: false }).ids.length, 'configured-tokenizer-content+framing-bound')
    } catch {
      const fallback = new TokenMeter(undefined, 'tokenizer-unavailable:utf8-upper-bound')
      fallback.fallbackUsed = true
      return fallback
    }
  }
  if (/^(gpt-|o1|o3|o4)/.test(model)) {
    try {
      const { encodingForModel } = await import('js-tiktoken')
      const encoding = encodingForModel(model as Parameters<typeof encodingForModel>[0])
      return new TokenMeter(text => encoding.encode(text, [], []).length, 'tiktoken-content+framing-bound')
    } catch { /* Unknown model: never substitute an unrelated tokenizer. */ }
  }
  return new TokenMeter()
}
