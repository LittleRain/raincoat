import { registerHttp } from './lib/http.js'
import { recoverRuns } from './lib/store.js'

export const inject = ['webServer', 'connection']

export function apply(ctx) {
  try {
    // 宿主重启后，跑了一半的 run 要显式标成中断，不能留在「执行中」
    recoverRuns()
    const dispose = registerHttp(ctx)
    ctx.effect(() => () => dispose())
  } catch (error) {
    console.error('[acg-capture] 初始化失败，抓取台不可用：', error?.message ?? error)
  }
}
