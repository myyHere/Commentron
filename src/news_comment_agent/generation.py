from __future__ import annotations

from .models import CandidateComment, CommentPattern, PostUnderstanding, VisualPrompt


def generate_candidate_comments(
    understanding: PostUnderstanding,
    patterns: list[CommentPattern]
) -> list[CandidateComment]:
    pattern_lookup = {pattern.style: pattern for pattern in patterns}
    summary = understanding.core_claim
    humor = understanding.humor_hooks[0] if understanding.humor_hooks else "headline exaggeration"
    debate = understanding.debate_hooks[0] if understanding.debate_hooks else "what readers would argue about"
    category = understanding.category

    if category == "deal":
        candidates = [
            CandidateComment(
                style="一针见血",
                body="翻译一下：这不是在卖 iPad，是在卖“再不下单你就亏了”的情绪。",
                target_emotion="认同感",
                expected_engagement="high",
                risk_notes="偏主观，可能被觉得在嘲讽促销读者。",
                rationale=f"把“{summary}”压成一句更像评论区会传播的话。"
            ),
            CandidateComment(
                style="抖机灵",
                body="苹果最懂的一件事，就是让你觉得自己不是在花钱，而是在“避免错过优惠”。",
                target_emotion="会心一笑",
                expected_engagement="medium-high",
                risk_notes="更像消费吐槽，需要读者熟悉苹果定价套路。",
                rationale=f"围绕“{humor}”做消费场景冷笑话。"
            ),
            CandidateComment(
                style="引发争论",
                body="问题可能不是这 150 美元值不值，而是 256GB 蜂窝版到底是不是大多数人最容易买贵的那个配置？",
                target_emotion="争辩欲",
                expected_engagement="high",
                risk_notes="会把讨论引向配置选择，可能偏离纯价格讨论。",
                rationale=f"直接把“{debate}”改写成能引出用户站队的话题。"
            ),
            CandidateComment(
                style="反问式",
                body="真有这么多人需要一台带蜂窝的 iPad Air，还是大家只是很难拒绝“历史低价”这四个字？",
                target_emotion="思考欲",
                expected_engagement="medium-high",
                risk_notes="会挑战用户购买动机，可能引发防御性回复。",
                rationale="保留疑问句结构，把焦点放在购买动机而不是参数表。"
            ),
        ]
    elif category == "earnings":
        candidates = [
            CandidateComment(
                style="一针见血",
                body="翻译一下：这份财报的问题不是增长不够猛，而是增长越来越像一门先烧钱、后讲故事的生意。",
                target_emotion="认同感",
                expected_engagement="high",
                risk_notes="措辞偏锐利，可能被多头认为过度悲观。",
                rationale=f"把“{summary}”压成一句更贴近投资讨论区的判断。"
            ),
            CandidateComment(
                style="抖机灵",
                body="AI 概念最烧的可能不是市场情绪，是资本开支和投资人耐心。",
                target_emotion="会心一笑",
                expected_engagement="medium-high",
                risk_notes="更像投资梗，非股市用户可能无感。",
                rationale=f"围绕“{humor}”做财报语境下的冷幽默。"
            ),
            CandidateComment(
                style="引发争论",
                body="如果营收和利润都很好看，但自由现金流塌了，这到底算基本面变强，还是只是把账单往后拖？",
                target_emotion="争辩欲",
                expected_engagement="high",
                risk_notes="会直接触发财务口径争论。",
                rationale=f"围绕“{debate}”把讨论拉到最核心的估值分歧上。"
            ),
            CandidateComment(
                style="反问式",
                body="再好的公司，如果估值已经默认它未来几年没有失误空间，那买的是业务，还是信仰？",
                target_emotion="思考欲",
                expected_engagement="medium-high",
                risk_notes="更适合投资评论区，不适合纯资讯摘要场景。",
                rationale="保留疑问句结构，把焦点放在估值和预期差。"
            ),
        ]
    else:
        candidates = [
            CandidateComment(
                style="一针见血",
                body="翻译一下：这新闻表面在讲事件，真正能带动评论的还是它背后的利益和动机。",
                target_emotion="认同感",
                expected_engagement="high",
                risk_notes="概括性强，可能被认为不够具体。",
                rationale=f"直接压缩文章核心观点，贴近“{summary}”。"
            ),
            CandidateComment(
                style="抖机灵",
                body="有些新闻是在报道事实，有些新闻是在提醒你大家会怎么表演性解读这件事。",
                target_emotion="会心一笑",
                expected_engagement="medium-high",
                risk_notes="偏抽象，需要读者接受元吐槽。",
                rationale=f"借用“{humor}”这个槽点做更通用的冷幽默。"
            ),
            CandidateComment(
                style="引发争论",
                body=_debate_line_from_hook(debate),
                target_emotion="争辩欲",
                expected_engagement="high",
                risk_notes="争议度高，容易把讨论拉向价值判断。",
                rationale=f"围绕“{debate}”把读者拉进讨论。"
            ),
            CandidateComment(
                style="反问式",
                body="真正值得问的，是这条新闻改变了什么，还是它只是把大家原本就相信的东西又放大了一遍？",
                target_emotion="思考欲",
                expected_engagement="medium-high",
                risk_notes="比较抽象，适合评论区而不是信息摘要。",
                rationale="保留怀疑语气，用问题推动回复。"
            ),
        ]

    # Pull one borrowed structural hint into the rationale for traceability.
    for item in candidates:
        pattern = pattern_lookup.get(item.style)
        if pattern:
            item.rationale = f"{item.rationale} 参考的互动模式：{pattern.structure}"
    return candidates


def create_visual_prompt(best_comment: CandidateComment, understanding: PostUnderstanding) -> VisualPrompt:
    visual_hook = understanding.visual_hooks[0] if understanding.visual_hooks else "A pristine corporate stage"
    if understanding.category == "deal":
        concept = "用促销海报语气和真实消费犹豫形成反差"
        prompt = (
            "Create a satirical consumer-tech illustration. "
            f"Scene: {visual_hook}. "
            "Show a glowing 'ALL-TIME LOW' sale tag pulling shoppers toward a tablet, while small fine print hints at upsell psychology. "
            f"Match the mood of this comment: {best_comment.body} "
            "Style should feel like a sharp retail editorial graphic, clean, modern, and slightly ironic."
        )
    elif understanding.category == "earnings":
        concept = "把亮眼财报和现金流压力放在同一张图里"
        prompt = (
            "Create a satirical financial editorial illustration. "
            f"Scene: {visual_hook}. "
            "Show a glossy earnings chart rising upward while a much smaller cash-flow pipe underneath is visibly cracking. "
            f"Match the mood of this comment: {best_comment.body} "
            "Style should feel like a sharp business-magazine cover, clean, analytical, and slightly cynical."
        )
    else:
        concept = "用企业光鲜表象对比规则灵活性的讽刺图"
        prompt = (
            "Create a satirical editorial illustration. "
            f"Scene: {visual_hook}. "
            "Add a velvet-rope VIP lane labeled 'special access' while ordinary people wait in a long standard line. "
            f"Overlay mood matching this comment: {best_comment.body} "
            "Style should feel like a sharp magazine cover, clean, ironic, and finance-news friendly."
        )
    return VisualPrompt(concept=concept, prompt=prompt)


def _debate_line_from_hook(debate: str) -> str:
    if debate.endswith("?"):
        return debate
    return f"{debate}？"
