from __future__ import annotations

from typing import List, Optional

from .poster_config import ASPECT_RATIOS, STYLE_MAP, TEMPLATES


def _template_meta(template_key: str) -> dict:
    for template in TEMPLATES:
        if template["key"] == template_key:
            return template
    return TEMPLATES[0]


def _position_label(position: Optional[str]) -> str:
    mapping = {
        "top_left": "左上角",
        "top_right": "右上角",
        "bottom_left": "左下角",
        "bottom_right": "右下角",
    }
    return mapping.get(position or "top_right", "右上角")


def _join_highlights(highlights: List[str]) -> str:
    normalized = [h.strip() for h in highlights if h.strip()]
    return "、".join(normalized) if normalized else "突出核心卖点"


def _resolve_style_desc(style_key: str) -> str:
    entry = STYLE_MAP.get(style_key)
    return entry["prompt_description"] if entry else style_key


def _build_dialogue_product_prompt(
    product_name: str,
    style_desc: str,
    ratio_label: str,
    ratio_size: str,
    character_hint: str,
    highlights_text: str,
) -> str:
    characters = character_hint if character_hint else "两位有表现力的角色"
    return f"""
请设计一张中文动画风格产品宣传海报。

【产品】{product_name}
【角色】{characters}
【卖点】{highlights_text}

【要求】
1. 产品必须是画面焦点。
2. 角色与产品有自然互动。
3. 可包含简短中文对话气泡。
4. 构图完整、适合营销海报。

【风格】
- {style_desc}
- 插画质感，非写实照片

【比例】{ratio_label}（{ratio_size}）
【禁止】水印、乱码、无关 logo。
""".strip()


def build_prompt(
    product_name: str,
    style: str,
    *,
    highlights_text: str = "",
    description_text: str = "",
    ratio_label: str = "方形",
    ratio_size: str = "1024x1024",
) -> str:
    style_desc = _resolve_style_desc(style)
    return _build_dialogue_product_prompt(
        product_name=product_name,
        style_desc=style_desc,
        ratio_label=ratio_label,
        ratio_size=ratio_size,
        character_hint=description_text,
        highlights_text=highlights_text,
    )


def build_poster_prompt(
    *,
    template_key: str,
    product_name: str,
    highlights: List[str],
    style: str,
    description: Optional[str],
    ratio_key: str,
) -> str:
    template = _template_meta(template_key)
    ratio = ASPECT_RATIOS.get(ratio_key, ASPECT_RATIOS["square"])
    highlights_text = _join_highlights(highlights)
    description_text = description.strip() if description else ""
    style_desc = _resolve_style_desc(style)
    merged_style = f"{style_desc}，整体基调：{template['tone']}"
    return build_prompt(
        product_name=product_name,
        style=merged_style,
        highlights_text=highlights_text,
        description_text=description_text,
        ratio_label=ratio["label"],
        ratio_size=ratio["size"],
    )


_PANEL_SCENES = [
    "角色发现痛点并注意到产品",
    "角色拿起产品并观察细节",
    "角色开始实际使用产品",
    "展示使用后的明显效果",
    "角色向他人推荐产品",
    "结尾定格，产品与角色同框",
]


def _build_panel_scenes(panel_count: int) -> List[str]:
    return _PANEL_SCENES[:panel_count]


def _infer_usage_context(product_name: str, product_description: str) -> str:
    text = f"{product_name} {product_description}".lower()
    mapping = [
        (("kitchen", "coffee", "cook", "厨", "餐", "咖啡"), "厨房或餐饮场景"),
        (("desk", "office", "办公", "学习", "书桌"), "办公或学习桌面场景"),
        (("outdoor", "travel", "camp", "户外", "旅行"), "户外活动场景"),
        (("beauty", "skincare", "cosmetic", "护肤", "美妆"), "梳妆台或浴室场景"),
        (("fitness", "sport", "gym", "健身", "运动"), "健身训练场景"),
    ]
    for keys, context in mapping:
        if any(key in text for key in keys):
            return context
    return "自然的日常使用场景"


def build_comic_storyboard(
    *,
    panel_count: int,
    product_name: str,
    product_description: str = "",
) -> List[dict]:
    context = _infer_usage_context(product_name=product_name, product_description=product_description)
    desc = product_description.strip() or f"{product_name} 的日常使用"
    beats = [
        {
            "scene": "需求出现",
            "camera": "大全景建立镜头",
            "action": f"角色在 {context} 中遇到痛点，注意力被产品吸引。",
            "emotion": "好奇",
            "dialogue_hint": "由模型根据本格剧情与情绪自由构思对白，避免固定模板句。",
            "continuity_note": "建立环境、角色服装与关键道具。",
        },
        {
            "scene": "产品出场",
            "camera": "中景，产品前置",
            "action": f"角色拿起 {product_name}，观察外观和关键细节。",
            "emotion": "惊喜",
            "dialogue_hint": "由模型根据本格剧情与情绪自由构思对白，避免固定模板句。",
            "continuity_note": "保持角色外观和产品形态一致。",
        },
        {
            "scene": "开始上手",
            "camera": "中近景",
            "action": f"角色开始在 {desc} 场景里实际使用 {product_name}。",
            "emotion": "专注",
            "dialogue_hint": "由模型根据本格剧情与情绪自由构思对白，避免固定模板句。",
            "continuity_note": "保持与上一格的空间连续关系。",
        },
        {
            "scene": "效果强化",
            "camera": "动态斜角镜头",
            "action": "通过前后对比，展示使用后的明显效果提升。",
            "emotion": "兴奋",
            "dialogue_hint": "由模型根据本格剧情与情绪自由构思对白，避免固定模板句。",
            "continuity_note": "动作与镜头变化要明显，但人物和产品一致。",
        },
        {
            "scene": "主动推荐",
            "camera": "双人中景",
            "action": f"主角色向同伴演示并推荐 {product_name}。",
            "emotion": "自信",
            "dialogue_hint": "由模型根据本格剧情与情绪自由构思对白，避免固定模板句。",
            "continuity_note": "新增角色时，主角色和产品仍是视觉中心。",
        },
        {
            "scene": "结尾定格",
            "camera": "收束特写镜头",
            "action": "角色与产品同框定格，形成海报级结尾画面。",
            "emotion": "满足",
            "dialogue_hint": "由模型根据本格剧情与情绪自由构思对白，避免固定模板句。",
            "continuity_note": "作为结尾格，构图稳定，画面完成度高。",
        },
    ]
    return [dict(beats[i], index=i + 1) for i in range(panel_count)]


def build_comic_panel_prompt(
    *,
    panel_index: int,
    panel_count: int,
    product_name: str,
    scene_description: str,
    style: str,
    character_hint: str = "",
    camera: str = "",
    action: str = "",
    emotion: str = "",
    dialogue: str = "",
    continuity_note: str = "",
    product_description: str = "",
    language: str = "zh-CN",
    text_mode: str = "post_render",
    ratio_label: str = "方形",
    ratio_size: str = "1024x1024",
) -> str:
    style_desc = _resolve_style_desc(style)
    characters = character_hint.strip() if character_hint.strip() else "1-2位角色（人物或拟人均可）"
    product_desc_text = product_description.strip() if product_description.strip() else "未提供补充描述"
    camera_text = camera.strip() if camera.strip() else "中景"
    action_text = action.strip() if action.strip() else scene_description
    emotion_text = emotion.strip() if emotion.strip() else "积极自然"
    dialogue_text = dialogue.strip() if dialogue.strip() else "请根据本格剧情与情绪自行构思一句自然对白，不要套用固定句子。"
    continuity_text = continuity_note.strip() if continuity_note.strip() else "保持角色与产品一致性"

    language_text = "简体中文" if language == "zh-CN" else "English"
    if text_mode == "post_render":
        dialogue_rule = "画面中不要渲染任何可读文字，只保留空白对话气泡区域。"
    else:
        dialogue_rule = (
            "对话气泡文字必须为简体中文，禁止出现英文。"
            if language == "zh-CN"
            else "All speech bubble text must be in English."
        )

    return f"""
漫画分镜第 {panel_index}/{panel_count} 格。

【语言】{language_text}
【产品】{product_name}
【产品描述】{product_desc_text}
【角色设定】{characters}
【本格目标】{scene_description}
【镜头】{camera_text}
【动作】{action_text}
【情绪】{emotion_text}
【对白】{dialogue_text}
【连续性说明】{continuity_text}
【文字策略】{dialogue_rule}

【画风】{style_desc}
- 单格漫画构图，线条清晰
- 保持同一世界观和角色一致性
- 本格必须与上一格形成明显推进，不可重复同姿势同机位

【硬性限制】
- 禁止水印、乱码、无关 logo
- 禁止写实摄影风格

【比例】{ratio_label}（{ratio_size}）
""".strip()


PRODUCT_SET_TYPES = {
    "main": "主图",
    "detail": "细节特写",
    "selling_point": "卖点图",
    "scene": "应用场景图",
    "spec": "规格信息图",
}


def build_product_set_prompt(
    *,
    image_type: str,
    product_name: str,
    style: str,
    ratio_key: str,
    highlights: List[str],
    description: Optional[str],
    scene_description: Optional[str],
    specs: List[str],
) -> str:
    ratio = ASPECT_RATIOS.get(ratio_key, ASPECT_RATIOS["square"])
    highlights_text = _join_highlights(highlights)
    description_text = description.strip() if description else "未提供"
    scene_text = scene_description.strip() if scene_description else "家居/办公/户外等自然场景"
    specs_text = "、".join([s.strip() for s in specs if s.strip()]) or "未提供"

    common = f"""
你是资深电商视觉设计师。
将参考图中的产品作为唯一主体，保持外观一致（形状、颜色、材质、结构）。

【产品】{product_name}
【风格】{_resolve_style_desc(style)}
【比例】{ratio['label']}（{ratio['size']}）
【卖点】{highlights_text}
【描述】{description_text}

【规则】
1. 不得替换产品，不得改变核心结构。
2. 产品主体必须清晰可见。
3. 不要出现水印、二维码、乱码、无关 logo。
""".strip()

    if image_type == "main":
        extra = """
【类型】主图
- 纯净背景或浅色渐变背景
- 产品完整展示，构图明确
- 商业打光，强调质感
""".strip()
    elif image_type == "detail":
        extra = """
【类型】细节特写
- 近距离视角，突出材质和做工
- 保留产品辨识度，避免抽象化
""".strip()
    elif image_type == "selling_point":
        extra = """
【类型】卖点图
- 用视觉元素表现核心卖点
- 保留少量留白，便于后续文案叠加
""".strip()
    elif image_type == "scene":
        extra = f"""
【类型】应用场景图
- 将产品置于真实使用环境
- 场景补充：{scene_text}
- 产品仍为画面焦点
""".strip()
    elif image_type == "spec":
        extra = f"""
【类型】规格信息图
- 展示产品整体及关键尺寸信息
- 规格信息：{specs_text}
- 信息层级清楚、排版整齐
""".strip()
    else:
        extra = "【类型】通用产品图"

    return f"{common}\n\n{extra}".strip()
