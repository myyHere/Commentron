# 系统设计说明

## 目标
构建一个可演示的新闻评论 Agent，完成三件事：
- 看懂新闻帖子与配图信息。
- 学习高互动评论的模式。
- 生成原创、可互动的“神评论”。

## 核心流程
1. `content_ingestion`
   接收样例、JSON 文件或 URL 文本输入，统一成 `NewsInput`。
2. `post_understanding`
   产出结构化“帖子理解对象”，包括摘要、核心观点、争议点、笑点/槽点、讨论切口、视觉线索。
3. `reddit_retrieval`
   根据话题标签检索本地 Reddit 评论语料，找出风格匹配且互动分高的参考评论。
4. `pattern_derivation`
   将参考评论提炼为模式库，保留风格、结构、适用场景和风险等级。
5. `comment_generation`
   基于帖子理解与模式库生成多风格候选评论。
6. `ranking`
   结合互动潜力、问句驱动、长度和风险进行排序。
7. `reporting`
   输出结构化 JSON 和面向展示的 Markdown 报告。
8. `publisher`
   第一版只预留扩展点，不真正调用平台。

## 数据结构
主要对象：
- `NewsInput`
- `PostUnderstanding`
- `RedditComment`
- `CommentPattern`
- `CandidateComment`
- `VisualPrompt`
- `PipelineResult`

这些对象都在 [src/news_comment_agent/models.py](/d:/vs_practive/2025study/TEST/ths_agent/src/news_comment_agent/models.py) 中定义，便于后续替换内部实现而不破坏流程接口。

## 关键设计决策
### 1. 中间层结构化输出
不让生成模型直接从新闻跳到评论，先产出明确的结构化分析层，保证：
- 可解释
- 可调试
- 可评估
- 可替换

### 2. 模式学习而非文本照搬
参考评论只用于提炼互动形式，例如：
- 反讽式总结
- 公平性质问
- 角色反转
- 干巴巴冷笑话

这样可以降低抄袭风险，也更符合“原创评论”目标。

### 3. 演示原型优先
第一版以“完整链路”和“高质量说明文档”为验收重点，所以优先保证：
- 样例一键可跑
- 输出清晰
- 模块边界稳定

而不是优先追求在线抓取、登录授权和真实发帖。

## 错误处理策略
- 输入异常：
  JSON 缺字段时直接抛错，避免静默生成错误内容。
- URL 抓取失败：
  返回明确异常，建议用户改用本地输入文件。
- 输出审查：
  候选评论保留 `risk_notes`，便于人工复核。

## 第二阶段已完成
- 新增后端抽象层：`HeuristicBackend` 和 `OpenAIBackend`。
- 新增 `RuntimeSettings`，统一管理后端、模型和 API 地址。
- 新增结构化 Prompt 组装模块，避免把 Prompt 散落在业务逻辑里。
- 新增多模态输入支持：
  `NewsInput` 现在可以带 `image_urls` 和 `local_image_paths`。
- 新增 LLM 排序能力：
  `openai` 后端可以直接对候选评论打分并返回最佳评论。

## 下一步扩展点
- 接入在线 Reddit 数据源。
- 增加 `publisher` 适配器。
- 增加人工审核工作流。
- 增加失败自动回退策略，例如 OpenAI 失败时自动切回 `heuristic`。
