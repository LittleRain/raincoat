# 运动片段交给 ChatCut

统一运动工作台在新建场次时选择足球或羽毛球，两种场次都通过“下载 ChatCut 交接清单”生成 JSON。清单引用本机原片，不会复制视频，也不是 ChatCut 原生工程文件。先在 ChatCut Desktop 的 `My Assets` 导入清单 `sources` 中的原片，再把清单作为本次编辑的参考交给 Agent。

清单的共同字段：

```json
{
  "schema_version": 1,
  "sport": "badminton",
  "sources": [{"id": "source-1", "name": "match.MOV", "path": "/absolute/path/match.MOV"}],
  "segments": [{"id": "rally-001", "source_id": "source-1", "start_s": 12.5, "end_s": 29.7,
                "segment_kind": "rally", "highlight": true,
                "identity_status": "confirmed_target", "note": "白衣黄裤球员连续防守后得分"}]
}
```

`start_s`、`end_s` 都是原片时间。足球还带 `action`、`session_name`；羽毛球还带 `mode`、`target_description`。只输出审核后“保留”的片段，并按工作台确认的顺序排列。导出后移动原片会使 `path` 失效，需在 ChatCut 重新定位素材。

交给 ChatCut Agent 的指令示例：

> 使用我已导入的原片和附上的交接清单，在新时间线上按 `segments` 顺序剪出每段 `start_s` 到 `end_s`。保留原片音画和完整连续动作。将 `highlight=true` 的片段标记为高光；把 `note` 当作编辑备注，先不要自动生成或虚构字幕。完成后让我检查时间线，暂不导出成片。请报告未能匹配的原片或时间码。

ChatCut Desktop 的 Agent 或本地 `chatcut_desktop` 连接适合本机原片工作流。若改用 ChatGPT 内托管的 ChatCut 插件，需要在对应项目中提供可访问的素材；清单中的本机绝对路径不能单独让托管项目读取原片。
