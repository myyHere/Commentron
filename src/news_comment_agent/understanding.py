from __future__ import annotations

import re

from .models import NewsInput, PostUnderstanding


def analyze_post(news_input: NewsInput) -> PostUnderstanding:
    body = news_input.body
    title = news_input.title
    sentences = _split_sentences(body)
    lowered = f"{title} {body}".lower()
    category = _detect_category(lowered)

    evidence = sentences[:3] if sentences else [body]
    summary = _build_summary(title, body)
    core_claim = _infer_core_claim(lowered, title, body, category)
    tone = _infer_tone(lowered, category)
    controversies = _infer_controversies(lowered, category)
    humor_hooks = _infer_humor_hooks(lowered, category)
    debate_hooks = _infer_debate_hooks(lowered, category)
    visual_hooks = [_normalize_visual_hook(item) for item in news_input.image_descriptions]
    if not visual_hooks and category == "deal":
        visual_hooks = ["Retail product promo framing with price-drop emphasis"]

    return PostUnderstanding(
        category=category,
        summary=summary,
        core_claim=core_claim,
        tone=tone,
        controversies=controversies,
        humor_hooks=humor_hooks,
        debate_hooks=debate_hooks,
        visual_hooks=visual_hooks,
        evidence=evidence,
        topic_keywords=_extract_topic_keywords(lowered, category),
    )


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _build_summary(title: str, body: str) -> str:
    lead = _split_sentences(body)
    if lead:
        return f"{title}. {lead[0]}"
    return title


def _detect_category(lowered: str) -> str:
    if any(re.search(pattern, lowered) for pattern in [
        r"\ball-time low\b",
        r"\bdiscount\b",
        r"\bdeal\b",
        r"\bprice drop\b",
        r"\b\d+\s*gb\b",
        r"\bcellular\b",
        r"\besim\b",
    ]):
        return "deal"
    if any(token in lowered for token in ["tariff", "policy", "carveout", "political", "election"]):
        return "policy"
    if any(token in lowered for token in ["earnings", "revenue", "guidance", "quarter"]):
        return "earnings"
    return "general"


def _infer_core_claim(lowered: str, title: str, body: str, category: str) -> str:
    if category == "deal":
        current_price, discount_amount = _extract_deal_numbers(body)
        if current_price and discount_amount:
            return (
                f"The article frames this as a notable retail deal: the product is available for "
                f"${current_price} with roughly ${discount_amount} off."
            )
        return "The article presents a consumer-tech price drop and emphasizes value, timing, and deal urgency."
    if category == "policy":
        return "The article suggests the headline business move may also be a strategic play for political or regulatory advantage."
    if category == "earnings":
        return "The article focuses on company performance and what investors think the numbers imply next."
    return f"The article centers on {title} and highlights the most discussion-worthy angle in the body text."


def _infer_tone(lowered: str, category: str) -> str:
    if category == "deal":
        return "promotional but informative"
    if category == "policy":
        if any(token in lowered for token in ["critics", "costly", "toll booth", "pays retail"]):
            return "skeptical and sharp"
        return "market-excited but cautious"
    if category == "earnings":
        return "investor-focused"
    return "analytical"


def _infer_controversies(lowered: str, category: str) -> list[str]:
    if category == "deal":
        controversies = []
        if any(token in lowered for token in ["all-time low", "deal", "discount"]):
            controversies.append("Is the discount genuinely exceptional or just retail anchoring?")
        if any(token in lowered for token in ["amazon", "apple card", "trade in", "installments"]):
            controversies.append("Are buyers saving money, or being nudged into a bigger ecosystem spend?")
        if any(token in lowered for token in ["256gb", "512gb", "1tb", "cell", "cellular"]):
            controversies.append("Does the discounted configuration actually match what most users need?")
        return controversies or ["Is the promotion actually worth the upgrade?"]
    if category == "policy":
        return _collect_matches(
            lowered,
            {
                "Policy favoritism": ["tariff", "relief", "carveout", "favorable rules", "applied evenly"],
                "Politics shaping business": ["election", "political", "signaling", "patriotic"],
                "Market hype versus real impact": ["markets", "rally", "headline", "investor excitement"],
            },
        )
    if category == "earnings":
        controversies = []
        if any(token in lowered for token in ["free cash flow", "fcf", "cash flow", "capex"]):
            controversies.append("Do strong earnings matter if cash conversion is deteriorating?")
        if any(token in lowered for token in ["valuation", "p/e", "price-to-sales", "ev/ebitda"]):
            controversies.append("Is the market already pricing in perfection?")
        if any(token in lowered for token in ["aws", "azure", "google cloud", "competition"]):
            controversies.append("Can the core growth engine stay dominant while competition accelerates?")
        return controversies or ["Are the headline results stronger than the underlying economics?"]
    return ["What is the real takeaway behind the headline?"]


def _infer_humor_hooks(lowered: str, category: str) -> list[str]:
    if category == "deal":
        hooks = []
        if any(token in lowered for token in ["all-time low", "discount", "off"]):
            hooks.append("Tech deals always sound life-changing until you remember you still did not need a new tablet")
        if any(token in lowered for token in ["256gb", "512gb", "1tb"]):
            hooks.append("Retailers know storage tiers are where self-control goes to die")
        if any(token in lowered for token in ["cell", "cellular", "esim"]):
            hooks.append("Adding cellular is the classic way to turn a deal into a monthly bill")
        return hooks or ["A discount headline doing its best to create urgency"]
    if category == "policy":
        return _collect_matches(
            lowered,
            {
                "Money as a shortcut to exceptions": ["100 billion", "costly", "buy certainty", "insurance premium"],
                "Patriotism as investor catnip": ["patriotic", "headline", "market", "rally"],
                "Corporate lobbying disguised as strategy": ["roadmap", "corporate strategy", "toll booth", "relief"],
            },
        )
    if category == "earnings":
        hooks = []
        if any(token in lowered for token in ["free cash flow", "fcf", "cash flow collapsed"]):
            hooks.append("Record revenue always sounds less magical when the cash register looks exhausted")
        if any(token in lowered for token in ["ai", "capex", "infrastructure"]):
            hooks.append("Every AI bull case eventually runs into the electricity bill")
        if any(token in lowered for token in ["valuation", "priced in", "multiple"]):
            hooks.append("The market loves flawless execution stories right until flawlessness gets expensive")
        return hooks or ["Great numbers with a catch hidden in the footnotes"]
    return ["The gap between headline framing and what people actually care about"]


def _infer_debate_hooks(lowered: str, category: str) -> list[str]:
    if category == "deal":
        hooks = []
        if any(token in lowered for token in ["all-time low", "discount"]):
            hooks.append("Is this a genuinely strong deal, or just the kind of price Apple shoppers were always going to talk themselves into?")
        if any(token in lowered for token in ["256gb", "cell", "cellular"]):
            hooks.append("Is 256GB cellular actually the smart sweet spot, or the upsell tier people regret later?")
        if any(token in lowered for token in ["m4", "new"]):
            hooks.append("At what point does 'latest chip' stop mattering more than how you actually use the device?")
        return hooks or ["Does this deal really justify the upgrade?"]
    if category == "policy":
        return _collect_matches(
            lowered,
            {
                "Is this genuine investment or a political fee?": ["investment", "political", "toll booth", "insurance"],
                "Do only giant firms get policy flexibility?": ["biggest companies", "certainty", "everyone else pays retail"],
                "Should investors celebrate rule-shopping?": ["markets", "strategy", "policy", "certainty"],
            },
        )
    if category == "earnings":
        hooks = []
        if any(token in lowered for token in ["free cash flow", "fcf", "cash flow"]):
            hooks.append("If free cash flow is collapsing, how much should investors still trust the headline beat?")
        if any(token in lowered for token in ["valuation", "priced in", "p/e", "multiple"]):
            hooks.append("At what valuation does 'great company' stop meaning 'great buy'?")
        if any(token in lowered for token in ["aws", "azure", "google cloud", "competition"]):
            hooks.append("Is AWS still a moat, or just the least vulnerable giant in a faster race?")
        return hooks or ["How much upside is left after a strong quarter?"]
    return ["What would make this story worth arguing about in the comments?"]


def _collect_matches(body: str, mapping: dict[str, list[str]]) -> list[str]:
    results = [label for label, keywords in mapping.items() if any(keyword.lower() in body for keyword in keywords)]
    return results or list(mapping)[:2]


def _normalize_visual_hook(text: str) -> str:
    stripped = text.strip()
    if stripped.endswith("."):
        stripped = stripped[:-1]
    return stripped


def _extract_deal_numbers(body: str) -> tuple[str | None, str | None]:
    current_price_match = re.search(
        r"(available|priced|now selling|sale price)[^$]{0,40}\$(\d[\d,]*)",
        body,
        re.IGNORECASE,
    )
    amounts = [match.replace(",", "") for match in re.findall(r"\$(\d[\d,]*)", body)]
    if not amounts:
        return None, None

    discount_match = re.search(
        r"\$(\d[\d,]*)\s+(discount|off|reduction)|"
        r"(discount|off|reduction)[^\$]{0,20}\$(\d[\d,]*)",
        body,
        re.IGNORECASE,
    )
    discount_amount = None
    if discount_match:
        discount_amount = discount_match.group(1) or discount_match.group(4)
        if discount_amount:
            discount_amount = discount_amount.replace(",", "")

    if current_price_match:
        current_price = current_price_match.group(2).replace(",", "")
        return current_price, discount_amount

    numeric_amounts = [int(amount) for amount in amounts]
    if discount_amount:
        discount_value = int(discount_amount)
        non_discount_values = [value for value in numeric_amounts if value != discount_value]
        if non_discount_values:
            current_price = str(max(non_discount_values))
            return current_price, discount_amount

    if len(numeric_amounts) >= 2:
        sorted_values = sorted(numeric_amounts, reverse=True)
        return str(sorted_values[0]), str(sorted_values[1])
    return amounts[0], None


def _extract_topic_keywords(lowered: str, category: str) -> list[str]:
    if category == "deal":
        return [token for token in ["deal", "discount", "price", "upgrade", "consumer", "tablet", "apple"] if token in lowered]
    if category == "policy":
        return [token for token in ["policy", "tariff", "regulation", "politics", "markets", "big tech"] if token in lowered]
    if category == "earnings":
        return [token for token in ["earnings", "revenue", "free cash flow", "valuation", "aws", "cloud", "capex", "investors"] if token in lowered]
    return [token for token in ["markets", "company", "strategy"] if token in lowered]
