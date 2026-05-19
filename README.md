# 新闻 URL 评论生成器

这个项目现在收缩为一条简单链路：
- 输入一条新闻 URL
- 抓取正文
- 分析帖子
- 检索相关 Reddit 评论模式
- 返回一条主推评论

命令行标准输出只返回最终评论正文。进度日志会输出到 `stderr`。

## 快速运行
要求：`Python 3.11+`

先复制配置：

```bash
cp agent_config.example.json agent_config.json
```

然后填写你自己的运行配置：
- `runtime.backend`
- `runtime.model`
- `runtime.api_base`
- `runtime.api_mode`
- `runtime.api_key`
- `runtime.proxy`
- `reddit.user_agent`

运行：

```bash
python3 main.py --url "https://example.com/news"
```

如果使用默认启发式模式，命令会直接返回一条评论。

如果使用 `openai` 后端，会额外调用你配置的模型完成分析、生成和排序。

## 当前行为
- 只接受 `--url`
- 只返回一条主推评论
- 不再支持 `--sample`
- 不再支持 `--input-file`
- 不再支持 `--text-file`
- 不再写 `result.json` 或 `report.md`

## Reddit 参考评论
- 优先通过搜索引擎查找相关 Reddit 帖子
- 再抓取帖子可读内容提取评论
- 如果在线检索失败，会回退到本地 Reddit 样例库

## 已知限制
- URL 抓取仍然是轻量解析，不适合所有动态网页
- Reddit 无凭证抓取依赖搜索结果和页面可读代理，稳定性弱于官方 API
- 某些站点会直接阻止抓取请求

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## 设计说明
见 [docs/design.md](/home/lrqing/myy/cms/Commentron/Commentron/docs/design.md)
