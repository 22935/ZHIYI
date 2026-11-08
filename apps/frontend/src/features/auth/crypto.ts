/**
 * 本机口令派生。使用 Web Crypto 的 PBKDF2-SHA256 + 每账号随机盐，
 * 浏览器 localhost / HTTPS 与 Node webcrypto 均可运行。
 *
 * 边界：这是「浏览器本机入口」的口令校验，不是服务端认证。账号库随浏览器
 * 存储存在，可被本机使用者清除；真实多用户场景必须由服务端签发会话。
 */

/** 迭代次数。约 60~120ms，足以挡住离线暴力猜解，又不拖慢登录手感。 */
export const PBKDF2_ITERATIONS = 120_000
const DERIVED_BITS = 256
const encoder = new TextEncoder()

const toHex = (buffer: ArrayBuffer | Uint8Array): string =>
  Array.from(new Uint8Array(buffer as ArrayBuffer))
    .map(byte => byte.toString(16).padStart(2, '0'))
    .join('')

const fromHex = (hex: string): Uint8Array => {
  if (!/^[0-9a-f]*$/i.test(hex) || hex.length % 2 !== 0) return new Uint8Array()
  const bytes = new Uint8Array(hex.length / 2)
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16)
  }
  return bytes
}

const subtle = (): SubtleCrypto => {
  const candidate = globalThis.crypto?.subtle
  if (!candidate) {
    throw new Error('当前环境不支持 Web Crypto，请在 localhost 或 HTTPS 下打开')
  }
  return candidate
}

export const randomSalt = (): string => {
  const bytes = new Uint8Array(16)
  if (!globalThis.crypto?.getRandomValues) throw new Error('当前环境不支持安全随机数')
  globalThis.crypto.getRandomValues(bytes)
  return toHex(bytes)
}

export const randomId = (): string =>
  globalThis.crypto?.randomUUID?.() ??
  `acct_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`

export async function derivePasswordHash(
  password: string,
  saltHex: string,
  iterations: number = PBKDF2_ITERATIONS
): Promise<string> {
  const keyMaterial = await subtle().importKey(
    'raw',
    encoder.encode(password) as BufferSource,
    'PBKDF2',
    false,
    ['deriveBits']
  )
  const bits = await subtle().deriveBits(
    {
      name: 'PBKDF2',
      hash: 'SHA-256',
      salt: fromHex(saltHex) as BufferSource,
      iterations
    },
    keyMaterial,
    DERIVED_BITS
  )
  return toHex(bits)
}

/** 定长字符串比较，避免按位短路泄露摘要前缀。 */
export function safeEqual(left: string, right: string): boolean {
  if (left.length !== right.length) return false
  let difference = 0
  for (let i = 0; i < left.length; i += 1) {
    difference |= left.charCodeAt(i) ^ right.charCodeAt(i)
  }
  return difference === 0
}
