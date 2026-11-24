/**
 * dsh-notify 的浏览器半边：轮询宿主的「打开会话」请求，收到后切到对应会话。
 *
 * 这个文件是 DSH 客户端模块格式（`window.__ModuleLoader__.load`），
 * 由宿主插件 `@local/dsh-notify` 的 `dsh.client` 声明加载。
 */
window.__ModuleLoader__.load({
  id: '@local/dsh-notify',
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;

    /** 默认轮询间隔：本机请求，够快又不打扰。 */
    const DEFAULT_POLL_INTERVAL_MS = 1200;

    /** 只依赖工作台导航服务。 */
    const inject = ['uiWorkspace'];

    /**
     * 启动轮询。宿主侧 `/dsh-notify/pending` 读一次就清空，所以不会重复跳。
     *
     * @param ctx - 客户端插件上下文。
     */
    function apply(ctx, config) {
      const configured = config && Number(config.pollIntervalMs);
      const interval = Number.isFinite(configured) && configured >= 50 ? configured : DEFAULT_POLL_INTERVAL_MS;
      let stopped = false;
      let timer;

      const schedule = () => {
        if (stopped) return;
        timer = setTimeout(tick, interval);
      };

      const tick = async () => {
        if (stopped) return;
        try {
          const response = await fetch('/dsh-notify/pending', {
            cache: 'no-store',
            credentials: 'same-origin',
          });
          if (response.ok) {
            const payload = await response.json();
            const sessionId = payload && typeof payload.sessionId === 'string' ? payload.sessionId : '';
            if (sessionId.length > 0) {
              try {
                ctx.uiWorkspace.openSession(sessionId);
                if (typeof window !== 'undefined' && typeof window.focus === 'function') window.focus();
              } catch (error) {
                console.warn('[dsh-notify] 打开会话失败：', error);
              }
            }
          }
        } catch {
          // 宿主重启或路由还没挂上时静默重试。
        }
        schedule();
      };

      schedule();
      ctx.effect(() => () => {
        stopped = true;
        clearTimeout(timer);
      }, 'dsh-notify: poll open requests');
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  },
});
