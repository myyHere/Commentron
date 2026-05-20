# Commentron

`Commentron` 是一个新闻 URL 评论生成原型。

当前实现聚焦一条最小链路：

1. 输入一条新闻链接
2. 抓取正文
3. 分析主题和表达角度
4. 检索相关 Reddit 评论参考
5. 生成多条候选评论
6. 排序并输出 1 条最终评论

命令行标准输出只打印最终评论正文。运行过程中的进度信息会输出到 `stderr`。

## 适用范围

这个项目现在适合：

- 快速给一条新闻 URL 生成一条评论草稿
- 对比 `heuristic` 和 `openai` 两种后端效果
- 在在线 Reddit 检索失败时，使用本地样例继续跑通流程

这个项目现在不适合：

- 批量处理大量链接
- 依赖高稳定性的网页抓取
- 把 Reddit 检索结果当成完整、可验证的数据源

## 运行要求

- Python `3.11+`
- 能访问目标新闻页面
- 如果使用 `openai` 后端，还需要可访问的模型接口和 API Key

项目没有额外的第三方 Python 依赖。

## 快速开始

在项目目录下先准备配置文件：

```bash
cp agent_config.example.json agent_config.json
```

然后按需修改 `agent_config.json`。

最小运行方式：

```bash
python3 main.py --url "https://example.com/news"
```

如果配置文件不存在，程序会退回默认配置：

- `backend`: `heuristic`
- `model`: `gpt-4.1-mini`
- `api_base`: `https://api.openai.com/v1/responses`

## 配置说明

配置文件示例：

```json
{
  "runtime": {
    "backend": "openai",
    "model": "deepseek-v4-flash",
    "api_base": "https://api.openai.com/v1/responses",
    "api_mode": "responses",
    "api_key": "sk-...",
    "proxy": null
  },
  "reddit": {
    "user_agent": "Commentron/0.1",
    "search_limit": 6,
    "comment_limit": 6
  }
}
```

`runtime` 字段：

- `backend`: `heuristic` 或 `openai`
- `model`: `openai` 后端使用的模型 ID
- `api_base`: 模型接口地址，支持 Responses 或 Chat Completions 风格
- `api_mode`: `responses` 或 `chat`，留空时会根据 `api_base` 推断
- `api_key`: API Key；也可以通过环境变量提供
- `proxy`: 可选 HTTP/HTTPS 代理地址

`reddit` 字段：

- `user_agent`: Reddit 检索请求头
- `search_limit`: 最多抓取多少个 Reddit 帖子
- `comment_limit`: 每个帖子最多提取多少条候选评论

`openai` 后端下，如果配置文件里没填 `api_key`，程序还会尝试读取这些环境变量：

- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`

代理也支持从这些环境变量读取：

- `OPENAI_HTTPS_PROXY`
- `OPENAI_PROXY`
- `HTTPS_PROXY`
- `https_proxy`

## 命令行参数

```bash
python3 main.py --url "https://example.com/news" [options]
```

可用参数：

- `--config`: 配置文件路径，默认 `agent_config.json`
- `--url`: 要抓取并分析的新闻 URL，必填
- `--backend`: `heuristic` 或 `openai`
- `--model`: 覆盖配置中的模型名
- `--api-base`: 覆盖配置中的接口地址
- `--api-mode`: 指定 `responses` 或 `chat`
- `--proxy`: 覆盖配置中的代理地址

命令行参数优先级高于配置文件。

## 两种后端

### `heuristic`

纯本地规则流程，不调用模型接口。

适合：

- 快速验证流程是否跑通
- 网络环境不方便直连模型接口时做基础调试

### `openai`

会调用模型接口完成：

- 新闻理解
- 评论候选生成
- 候选排序

使用这个后端时，必须提供可用的 `api_key`。

## 抓取与回退逻辑

新闻抓取当前是轻量实现：

- 先直接请求目标 URL
- 遇到常见重定向时会继续跟随
- 某些页面抓取失败时，会尝试走 `https://r.jina.ai/` 的 reader 代理
- 对知乎回答页，遇到 `403` 时会尝试知乎 answer API

Reddit 参考评论检索当前流程：

- 通过 DuckDuckGo 搜索相关 Reddit 帖子
- 用 `r.jina.ai` 抓取帖子文本
- 提取可用评论行
- 如果在线结果为空，回退到本地样例库

这意味着结果质量会受到新闻页面可抓取性、搜索结果质量、reader 代理稳定性的影响。

## 输出行为

程序最终只输出一条评论正文，例如：

```text
This keeps getting framed as smart industrial policy, but it still looks like a pay-to-play loophole that only the biggest companies can afford.
```

进度日志类似下面这样，会打印到 `stderr`：

```text
[progress] Fetching URL: https://example.com/news
[progress] Starting pipeline with backend=heuristic
[progress] Understanding post with backend: heuristic
```

## 测试

在项目目录下运行：

```bash
python3 -m unittest discover -s tests -v
```

当前测试覆盖的重点包括：

- pipeline 能返回最终评论
- Reddit 在线检索和本地回退
- 配置文件读取
- 新闻抓取失败后的回退逻辑
- OpenAI 后端缺少 API Key 时的报错

## 已知限制

- 网页正文提取依赖简单规则，不保证适配所有站点
- 动态页面、强反爬站点、登录态页面可能直接失败
- Reddit 无官方 API 接入，稳定性取决于搜索结果和 reader 代理
- 最终只输出 1 条评论，不提供结构化结果导出

## 相关文档

- [设计说明](./docs/design.md)
- [提示词说明](./docs/prompts.md)
