## 0.1.1

修「点通知只会把窗口唤到前台，不切回那条会话」。

DSH 0.2.3-alpha.2 起，`webServer.register()` 的路由默认按 `required` 做准入，而点击命令是没有浏览器 Cookie 的本机 `curl`：请求在准入层就被 `401 unauthorized` 掉，根本到不了 `lib/http.js` 的 handler，`/dsh-notify/pending` 永远是空的。实测同端口下 `GET /dsh-notify/pending`、`POST /dsh-notify/open` 都是 401，而同样没登录态的未知路径是 404，说明拦截点就在这条路由的准入，不是 handler。

- **路由声明准入策略**：`/dsh-notify` prefix 路由加 `auth: routeAuth` —— `POST /open` 走 `anonymous`（身份仍由 `x-dsh-notify-token` 校验），`GET /pending` 保持 `required`，前端轮询照旧靠浏览器 Cookie 通过。
- **origin 与令牌改成点击时读文件**：命令原来把 `http://127.0.0.1:<发通知时的端口>` 写死进 `-execute`，Desktop 每次启动换端口，重启后点通知中心的旧通知只会打到一个没人监听的地址。现在插件把当前 origin 落盘到 `~/.dsh/notify/origin`，命令里写成 `$(/bin/cat …origin)`；令牌同理，避免 reload 换了新令牌后旧命令校验失败。
- `scripts/open-session.js` 默认读同一个 origin 文件，不要再手填端口。
- 新增 `test/index.test.js`：直接对挂载层断言路由带了 `auth: routeAuth`、origin 落盘、端口未就绪/配置非法时不影响挂载。这两个契约丢掉任意一个，点击都会静默退化成"只唤起窗口"。

已知限制：App 已退出时点击不会留下待打开请求；旧通知在 App 重启后能落到新端口，但会话若已被删除则静默失败（客户端 `openSession` 的异常只打 console）。
