# Raincoat Watch Recorder

个人 Apple Watch 录音与本地转写产品，将可追溯的对话文字交给现有 Obsidian 知识库。

**当前状态：需求已确认，尚未实现应用。** 本目录只包含产品定义和实施顺序，不代表录音、同步或转写已能运行。

- [产品定义与验收要求](docs/product-spec.md)
- [分阶段实施计划](docs/implementation-plan.md)

目标链路：Apple Watch → iPhone 暂存 → Mac 本地处理 → `ob_vault/00 Inbox/`。

目标设备为 Apple Watch Series 10 GPS、iPhone 15 Pro，以及 M5 / 32 GB Mac。录音系统版本和开发签名环境在首次实机验证时记录。

原音、声音档案和运行数据库保存在源码仓库外的本机数据目录。产品负责采集、转写、说话人标识、纠错与文件交付；知识提炼、Wiki 更新和知识问答由已有知识库流程负责。
