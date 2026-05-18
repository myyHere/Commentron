# Prompt 设计草案

当前仓库默认用规则和模板保证离线可跑，但如果切换到真实 LLM，推荐使用以下 Prompt 结构。

## 1. 帖子理解 Prompt
目标：把新闻转成结构化分析对象，而不是直接写评论。

```text
你是一个擅长拆解新闻舆论点的分析助手。
请阅读以下新闻标题、正文和图片描述，输出 JSON：
- summary
- core_claim
- tone
- controversies
- humor_hooks
- debate_hooks
- visual_hooks
- evidence

要求：
1. 不要复述整篇文章，要提炼出适合评论区互动的切口。
2. humor_hooks 要偏“槽点/梗点”。
3. debate_hooks 要偏“容易引发回复的问题”。
4. visual_hooks 只保留和评论创作有帮助的信息。
```

## 2. Reddit 互动模式提炼 Prompt
目标：从参考评论中提炼结构，不直接抄句子。

```text
你会收到一个新闻主题和若干高互动 Reddit 评论。
请提炼每条评论的：
- style
- structure
- when_to_use
- risk_level
- example_pattern

要求：
1. 学习的是互动模式，不是原句。
2. 结构描述要抽象到可迁移。
3. risk_level 用 low / medium / high。
```

## 3. 评论生成 Prompt
目标：生成多风格候选评论。

```text
基于以下输入生成 4 条原创评论：
- 帖子理解对象
- 评论模式库

四条评论风格必须分别是：
1. 一针见血
2. 抖机灵
3. 引发争论
4. 反问式

输出字段：
- style
- body
- target_emotion
- expected_engagement
- risk_notes
- rationale

要求：
1. 不要照抄参考评论。
2. 每条评论都要和新闻事实强相关。
3. 语气可以犀利，但不要无意义辱骂。
4. 优先让读者想回复，而不是单纯押韵或玩梗。
```

## 4. 评论评审 Prompt
目标：选择主推评论。

```text
请从候选评论中选出最适合公开发布的一条，并给出排序理由。
考量维度：
- 事实贴合度
- 互动潜力
- 风格鲜明度
- 原创性
- 安全风险
```
