/** OS-held lock: process death releases ownership; no stale-PID lock stealing. */
import koffi from 'koffi'
import { openSync, closeSync, realpathSync } from 'node:fs'
import { join } from 'node:path'

export function lockDataDirectory(directory: string): () => void {
  const path = join(realpathSync(directory), 'writer.lock')
  if (process.platform === 'win32') {
    const kernel = koffi.load('kernel32.dll')
    const create = kernel.func('void* __stdcall CreateFileW(str16, uint32, uint32, void*, uint32, uint32, void*)')
    const close = kernel.func('bool __stdcall CloseHandle(void*)')
    const handle = create(path, 0xc0010000, 0, null, 4, 0x04000080, null)
    if (handle === null || koffi.address(handle) === 0xffffffffffffffffn) throw new Error('HANDS_LEDGER_ALREADY_OWNED')
    return () => { close(handle) }
  }
  const fd = openSync(path, 'a')
  const libc = koffi.load(null)
  const flock = libc.func('int flock(int, int)')
  if (flock(fd, 6) !== 0) { closeSync(fd); throw new Error('HANDS_LEDGER_ALREADY_OWNED') }
  return () => { closeSync(fd) }
}
