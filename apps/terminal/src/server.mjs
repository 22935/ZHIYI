import { createServer } from 'node:http'
import { timingSafeEqual } from 'node:crypto'

export function createTerminalServer(sessions, token) {
  if (typeof token !== 'string' || token.length < 32) throw new Error('Terminal credential is required')
  const expected = Buffer.from('Bearer ' + token)
  return createServer(async (request, response) => {
    const send = (status, data) => {
      response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' })
      response.end(JSON.stringify(data))
    }
    try {
      const url = new URL(request.url, 'http://127.0.0.1')
      if (request.method === 'GET' && url.pathname === '/health') return send(200, { status: 'UP', service: 'zhiyi-terminal-host' })
      const supplied = Buffer.from(request.headers.authorization || '')
      if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return send(401, { error: 'Terminal authentication required' })
      const owner = request.headers['x-terminal-owner']
      if (typeof owner !== 'string' || !/^[a-zA-Z0-9-]{1,100}$/.test(owner)) return send(400, { error: 'Terminal owner is required' })
      let bytes = 0
      const chunks = []
      for await (const chunk of request) {
        bytes += chunk.length
        if (bytes > 128 * 1024) return send(413, { error: 'Terminal request is too large' })
        chunks.push(chunk)
      }
      const body = bytes ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}
      if (request.method === 'GET' && url.pathname === '/profiles') return send(200, { profiles: sessions.profileViews() })
      if (request.method === 'GET' && url.pathname === '/sessions') return send(200, { sessions: sessions.list(owner) })
      if (request.method === 'POST' && url.pathname === '/sessions') return send(201, sessions.create(owner, body))
      if (request.method === 'DELETE' && url.pathname === '/sessions') { sessions.closeOwner(owner); return send(200, { closed: true }) }
      const match = /^\/sessions\/([a-f0-9-]+)(?:\/(output|input|resize))?$/.exec(url.pathname)
      if (match) {
        const [, id, operation] = match
        if (request.method === 'GET' && operation === 'output') return send(200, sessions.read(owner, id, Number(url.searchParams.get('after') || 0)))
        if (request.method === 'POST' && operation === 'input') { sessions.write(owner, id, body.data); return send(200, { accepted: true }) }
        if (request.method === 'POST' && operation === 'resize') { sessions.resize(owner, id, body.cols, body.rows); return send(200, { resized: true }) }
        if (request.method === 'DELETE' && !operation) { sessions.close(owner, id); return send(200, { closed: true }) }
      }
      send(404, { error: 'Terminal endpoint not found' })
    } catch (error) {
      send(error.status || 400, { error: error.message || 'Terminal operation failed' })
    }
  })
}
