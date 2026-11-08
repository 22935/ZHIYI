import { readFileSync, unlinkSync } from 'node:fs'
import * as pty from 'node-pty'
import { TerminalSessions } from './sessions.mjs'
import { createTerminalServer } from './server.mjs'

const index = process.argv.indexOf('--config')
if (index < 0 || !process.argv[index + 1]) throw new Error('Usage: node src/main.mjs --config <local-config>')
const config = JSON.parse(readFileSync(process.argv[index + 1], 'utf8'))
if (!Number.isInteger(config.port) || config.port < 1 || config.port > 65535) throw new Error('Invalid terminal port')
const token = readFileSync(config.tokenFile, 'utf8').trim()
unlinkSync(config.tokenFile)
const sessions = new TerminalSessions(pty, { defaultCwd: config.defaultCwd })
const server = createTerminalServer(sessions, token)
server.listen(config.port, '127.0.0.1', () => console.log('Terminal Host ready on loopback port ' + config.port))
let stopping = false
function stop() {
  if (stopping) return
  stopping = true
  sessions.dispose()
  server.close(() => process.exit(0))
  server.closeAllConnections()
}
process.on('SIGINT', stop)
process.on('SIGTERM', stop)
process.on('SIGHUP', stop)
