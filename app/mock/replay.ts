/**
 * Mock engine server: replays a scripted scenario over ws://localhost:8787,
 * speaking the exact contract in shared/contracts/events.ts ({type, payload} both ways).
 *
 *   npm run mock                  # scenario "full" (happy path, then off-track)
 *   npm run mock -- happy         # or: happy | offtrack | full
 *   PORT=8787 npm run mock -- offtrack
 */
import { WebSocketServer, type WebSocket } from 'ws'
import { createMockEngine } from './engine'
import { scenarios, type ScenarioName } from './scenarios'
import type { Outgoing } from '../src/common/wire'

const name = (process.argv[2] ?? process.env.SCENARIO ?? 'full') as ScenarioName
const scenario = scenarios[name]
if (!scenario) {
  console.error(`Unknown scenario "${name}". Pick one of: ${Object.keys(scenarios).join(', ')}`)
  process.exit(1)
}
const port = Number(process.env.PORT ?? 8787)

const wss = new WebSocketServer({ port })
console.log(`[mock] scenario "${name}" on ws://localhost:${port}`)

wss.on('connection', (ws: WebSocket) => {
  console.log('[mock] client connected')
  const engine = createMockEngine(scenario, (e) => ws.readyState === ws.OPEN && ws.send(JSON.stringify(e)), true)
  ws.on('message', (data) => {
    try {
      engine.handle(JSON.parse(String(data)) as Outgoing)
    } catch (err) {
      console.warn('[mock] bad message', String(data), err)
    }
  })
  ws.on('close', () => {
    engine.stop()
    console.log('[mock] client disconnected')
  })
  engine.start()
})
