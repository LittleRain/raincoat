# 圈子业务日报需求

### 任务目标

每天根据输入的业务数据，对指定课题进行分析，并输出一个可交互的html页面

**业务介绍：** 圈子是一个B站会员购的内容社区业务，主要针对二次元线下活动（如漫展）、绘画、模型、谷子的品类爱好者提供交流的场域，主要目标是提升DAU和浏览深度。主要关注以下用户路径下的用户规模

用户场景介绍：
- **T3入口**：在B站app的会员购tab有一个固定的同好圈入口，会根据用户的历史行为确定暴露的圈子，用户点击后会进入到某个圈子的首页，如https://mall.bilibili.com/neul-next/circle/index.html?page=circle_home&noTitleBar=1&circleName=circle_paint
- **票务商详**：用户会在B站购买二次元线下项目的门票，在票务项目商详有一个讨论区（即“圈子”）的入口，可以先看到多个内容卡片，如果感兴趣可以点击“查看所有内容”，以进入漫展圈的某个项目tab。这个场景下，用户的意图比较明确

---

### 输入:
- 表格1：绘画圈feed_主动访问
  - 文件名：含“拉取绘画圈feed流明细数据”
  - 定义：昨天绘画圈feed流用户的浏览数据 by内容
  - 字段：content_id, title, subtitle, pubtime: 发布时间, item_id: 展会项目ID, item_name: 展会项目名称, cover:内容封面图url, 发布来源, 内容类型, 曝光pv, 点击pv, pv_ctr, pv互动数
- 表格2：模型圈feed_主动访问
  - 文件名：含“拉取模型圈feed流明细数据”
  - 定义：昨天模型圈feed流用户的浏览数据 by内容
  - 字段：content_id, title, subtitle, pubtime: 发布时间, item_id: 展会项目ID, item_name: 展会项目名称, cover:内容封面图url, 发布来源, 内容类型, 曝光pv, 点击pv, pv_ctr, pv互动数
- 表格3：漫展圈feed_主动访问
  - 文件名：含“拉取漫展圈feed流明细数据”
  - 定义：昨天从T3入口进入漫展圈的feed流用户的浏览数据 by内容
  - 字段：content_id, title, subtitle, pubtime: 发布时间, item_id: 展会项目ID, item_name: 展会项目名称, cover:内容封面图url, 发布来源, 内容类型, 曝光pv, 点击pv, pv_ctr, pv互动数
- 表格4：漫展圈_票务商详转化
  - 文件名：含“拉取漫展项目的转化行为数据”
  - 定义：昨天票务商详到漫展圈的转化数据 by项目
  - 字段：item_id:展会项目ID, item_name:展会项目名称, topic_id:展会话题ID, start_time:展会开始时间, 想去数, 商详浏览uv, 讨论区曝光uv, 讨论区点击uv, uv_ctr
- 表格5：漫展圈feed_票务商详
  - 文件名：含“拉取漫展圈feed流明细数据_票务商详”
  - 定义：昨天从票务商详到漫展圈后，用户在feed流的浏览数据，by内容
  - 字段：log_date:浏览日期, content_id, title, content_text, cover, filter_text:分区名称 , item_id:展会项目ID , item_name:展会项目名称, start_time:展会开始时间, uv_expose, uv_click, uv_ctr, pv_ctr


---

### 输出
表格1：总览
- by圈子展示整体情况
- 字段：曝光、点击、CTR、互动率
- 结论：从用户场景的角度分析有什么特征、从内容角度

表格2：绘画圈内容分析
- 展示曝光率较大的内容top10，标题、副标题、发布时间、曝光PV、点击PV、pv_ctr、互动数、链接
  - 链接的拼接规则：https://www.bilibili.com/opus/ + content_id
- 分析内容上有什么共性，比如用户都爱点击xx类型的内容

表格3：模型圈内容分析
- 展示曝光率较大的内容top10，标题、副标题、发布时间、曝光PV、点击PV、pv_ctr、互动数、链接
  - 链接的拼接规则：https://www.bilibili.com/opus/ + content_id
- 分析内容上有什么共性，比如用户都爱点击xx类型的内容

表格4：漫展圈内容分析
- T3路径下，展示曝光率较大的内容top10，标题、副标题、发布时间、曝光PV、点击PV、pv_ctr、互动数、链接
  - 链接的拼接规则：https://www.bilibili.com/opus/ + content_id
- 票务商详路径下，展示曝光率较大的内容top10，标题、副标题、发布时间、曝光PV、点击PV、pv_ctr、互动数、链接
  - 链接的拼接规则：https://www.bilibili.com/opus/ + content_id
- 分析内容上有什么共性，比如用户都爱点击xx类型的内容
- 分析不同渠道下用户爱看的内容上有什么差异

表格5：项目转化分析
- 展示访问量最大的项目top10，标题、副标题、发布时间、曝光PV、点击PV、pv_ctr、互动数、链接
  - 链接的拼接规则：https://www.bilibili.com/opus/ + content_id
- 从多个角度分析为什么某个项目的转化率高，为什么有的项目转化率低，挑有代表性的项目。角度可以有：开展时间、内容类型等