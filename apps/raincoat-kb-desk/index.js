// raincoat-kb-desk host 半片：/kb-desk/api 读写本地 vault，并驱动摄入队列与模型。
//
// 绝不能抛异常：DSH 的 web boot 在任一 entry 激活失败时会整体中止，表现为
// 「web boot: 1 entry did not activate」。面板不可用只是功能降级，拖垮 host 才是事故。
import { registerHttp } from './lib/http.js'
import { startWatcher } from './lib/watcher.js'

export const inject = ['webServer', 'connection']

export function apply(ctx) {
  try {
    ctx.effect(() => registerHttp(ctx), 'raincoat-kb-desk: /kb-desk/api routes')
    // Hermes 退役后，抓取之后的 pull / 整理 / 写入 / 推送由这个定时器接管。
    ctx.effect(() => startWatcher(ctx), 'raincoat-kb-desk: 自动摄入闭环')
  } catch (error) {
    console.error('[raincoat-kb-desk] 初始化失败，知识库面板将不可用：', error?.message ?? error)
  }
}
