# 后续分析接口契约（设计，P0 未实现）
P0 不调用任何检测器、跟踪器或多模态服务。
P1 建议 Python Protocol：analyze(request: AnalysisRequest) -> Iterable[Candidate]。
AnalysisRequest：session_id、media_id、proxy_path、sample_times、target_annotation、cloud_consent（默认 false）。
Candidate：type、start、end、source_media_ids、evidence、confidence、identity_status（unknown/uncertain/confirmed）、provider_id。
unknown 不能转成 confirmed；无可见进球证据不得输出确定的 goal。
本地 provider 不需要密钥。云 provider 在用户同意并说明具体帧/短片范围后才能接收衍生数据；禁止传原始视频。
真实视频标注评测通过前不得声称 AI 检测有效。此文档仅约定扩展边界，开发需另获 P1 授权。
