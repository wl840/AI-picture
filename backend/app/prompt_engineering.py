from __future__ import annotations

from typing import List, Optional

from .poster_config import ASPECT_RATIOS, TEMPLATES


def _template_meta(template_key: str) -> dict:
    for template in TEMPLATES:
        if template["key"] == template_key:
            return template
    return TEMPLATES[0]


def build_poster_prompt(
    *,
    template_key: str,
    product_name: str,
    highlights: List[str],
    style: str,
    description: Optional[str],
    ratio_key: str,
    logo_filename: Optional[str] = None,
) -> str:
    template = _template_meta(template_key)
    ratio = ASPECT_RATIOS.get(ratio_key, ASPECT_RATIOS["square"])

    highlights_text = "；".join([h.strip() for h in highlights if h.strip()]) or "突出核心价值"
    description_text = description.strip() if description else ""

    if logo_filename:
        logo_rule = (
            f"\n[Logo 规则]\n"
            f"- 已上传品牌 logo 文件：{logo_filename}。\n"
            f"- logo 仅作为角标使用，放在右下角或右上角。\n"
            f"- logo 宽度约为画面宽度 5%-8%，不得放大居中，不得作为主视觉主体。\n"
            f"- 保持 logo 原有形状与可识别性，不得拉伸变形。"
        )
    else:
        logo_rule = (
            "\n[Logo 规则]\n"
            "- 本次无 logo 输入，不要生成 logo 占位框，不要绘制中间圆形徽章。"
        )

    return f"""
你是一名资深品牌视觉设计师，请根据以下信息生成一张中文营销海报图像。

[海报目标]
- 模板类型：{template['name']}（{template['description']}）
- 视觉语气：{template['tone']}
- 风格：{style}
- 尺寸比例：{ratio['label']}，建议画布 {ratio['size']}

[素材信息]
- 名称：{product_name}
- 核心卖点：{highlights_text}
- 补充描述：{description_text if description_text else '无'}
{logo_rule}

[文案与排版规则]
1. 只输出自然营销文案，不要出现字段标签词。
2. 严禁出现“产品/活动名称”“核心卖点”“补充描述”“行动号召（CTA）”“模板”“字段”等提示词原文。
3. 文案层级清晰：主标题、副标题、卖点短句、行动号召。
4. 保留适度留白，主体突出，风格和配色统一。
5. 输出高质量可直接投放的海报图，文字清晰可读，不乱码。
""".strip()
