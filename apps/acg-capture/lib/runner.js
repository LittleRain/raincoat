import { spawn } from 'node:child_process'
import os from 'node:os'
import path from 'node:path'

import { BAG_ENGINE, ENGINE, ROOT, VG_ENGINE, newRunId } from './store.js'

/** runId -> { child, stderr, startedAt }；宿主重启后自然清空。 */
const children = new Map()
const lastStderr = new Map()

function envWithPath() {
  const extra = [path.join(os.homedir(), '.local', 'bin')]
  return { ...process.env, PATH: [...extra, process.env.PATH || ''].join(':') }
}

export function isRunning(runId) {
  return children.has(runId)
}

export function startRun({ kind, write = false, batch = 3, since = '', trigger = 'manual', leads = '', lanes = '', modes = '', windowDays = 0, mode = '' }) {
  const bag = kind === 'bag-discover'
  const vg = kind === 'vg-discover'
  if (!bag && !vg && !['backfill', 'discover'].includes(kind)) throw new Error(`未知任务：${kind}`)
  const runId = newRunId(kind)
  const args = bag
    ? [BAG_ENGINE, '--kind', 'discover', '--run-id', runId, '--trigger', trigger, '--lanes', lanes || 'workbuddy,deepseek']
    : vg
      ? [VG_ENGINE, '--kind', 'discover', '--run-id', runId, '--trigger', trigger, '--lanes', lanes || 'workbuddy,deepseek']
      : [ENGINE, '--kind', kind, '--run-id', runId, '--batch', String(batch), '--trigger', trigger,
         '--lanes', lanes || 'workbuddy,deepseek']
  if (vg && Number(windowDays) > 0) args.push('--window-days', String(windowDays))
  if (vg && mode === 'discover') args.push('--discover-only')
  if (write) args.push('--write')
  if (since) args.push('--since', since)
  if (bag && leads) args.push('--leads', leads)
  // 只跑其中一套 workbuddy 任务时用得上：sweep 全量扫街 / channel 定向渠道
  if (bag && modes) args.push('--modes', modes)

  const child = spawn('python3', args, {
    cwd: ROOT,
    env: envWithPath(),
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const record = { child, stderr: '', startedAt: Date.now() }
  children.set(runId, record)

  child.stdout.on('data', () => {})
  child.stderr.on('data', (chunk) => {
    record.stderr = (record.stderr + chunk.toString()).slice(-4000)
  })
  child.on('exit', () => {
    // stderr 留着：POST /runs 失败时要把它带回前端，否则用户只看到「启动失败」
    lastStderr.set(runId, record.stderr)
    if (lastStderr.size > 20) lastStderr.delete(lastStderr.keys().next().value)
    children.delete(runId)
  })
  child.on('error', (error) => {
    record.stderr = `${record.stderr}\nspawn error: ${error.message}`
    children.delete(runId)
  })
  return { runId, pid: child.pid }
}

export function stopRun(runId) {
  const record = children.get(runId)
  if (!record) return false
  try {
    record.child.kill('SIGTERM')
  } catch {
    // 进程已经退出
  }
  return true
}

export function runningIds() {
  return [...children.keys()]
}

export function stderrOf(runId) {
  return children.get(runId)?.stderr || lastStderr.get(runId) || ''
}
