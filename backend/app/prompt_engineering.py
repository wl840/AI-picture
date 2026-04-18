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
    return "；".join([h.strip() for h in highlights if h.strip()]) or "突出核心卖点"


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
    characters = character_hint if character_hint else "两个或更多角色（人物或动物均可）"
    return f"""
设计一张动画风格产品宣传海报。

【画面主体】
产品：{product_name}
{characters}正在使用或展示该产品，形成对话或互动场景
角色表情生动，肢体语言自然，场景富有叙事感

【核心要求】
1. 产品必须突出，作为画面焦点
2. 角色与产品的互动自然，体现产品的使用场景
3. 整体构图完整，具备海报视觉张力

【风格】
- {style_desc}
- 插画海报质感

【布局】
- 产品置于构图显眼位置，角色围绕产品互动
- 背景与角色风格统一，层次丰富但不喧宾夺主

【禁止】
- 不要出现无关文字、水印或logo
- 不要生成写实照片风格
- 不要模板化空白占位结构

【补充信息】
- 比例：{ratio_label}（{ratio_size}）
- 产品卖点：{highlights_text if highlights_text else "无"}
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
    merged_style = f"{style_desc}，{template['tone']}"
    return build_prompt(
        product_name=product_name,
        style=merged_style,
        highlights_text=highlights_text,
        description_text=description_text,
        ratio_label=ratio["label"],
        ratio_size=ratio["size"],
    )


PRODUCT_SET_TYPES = {
    "main": "主图",
    "detail": "细节特写",
    "selling_point": "卖点图",
    "scene": "产品应用场景图",
    "spec": "尺寸规格图",
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
    description_text = description.strip() if description else ""
    scene_text = scene_description.strip() if scene_description else ""
    specs_text = "；".join([s.strip() for s in specs if s.strip()]) or "未提供"

    common = f"""
你是资深电商视觉设计师。将参考图中的产品作为唯一主体，保持产品外观一致（形状、颜色、材质、结构）。

【产品】
- 名称：{product_name}
- 风格：{_resolve_style_desc(style)}
- 比例：{ratio['label']}（{ratio['size']}）
- 卖点：{highlights_text}
- 描述：{description_text if description_text else '无'}

【严格要求】
1. 不得替换产品，不得改变产品核心结构
2. 产品主体必须清晰可见，构图专业
3. 不要出现水印、乱码、品牌logo、二维码
4. 除尺寸规格图外，尽量不出现大段文字
""".strip()

    if image_type == "main":
        extra = """
【画面类型】主图
- 纯净背景或浅色渐变背景
- 产品完整展示，居中或黄金分割构图
- 商业广告级打光，强调质感
""".strip()
    elif image_type == "detail":
        extra = """
【画面类型】细节特写
- 近距离微距视角，放大材质与做工细节
- 可使用浅景深，突出纹理与结构
- 保留产品辨识度，避免抽象化
""".strip()
    elif image_type == "selling_point":
        extra = """
【画面类型】卖点图
- 用构图和视觉元素表现卖点，不依赖长文字
- 画面预留少量留白，便于后期补充文案
- 重点突出性能、材质或功能亮点
""".strip()
    elif image_type == "scene":
        extra = f"""
【画面类型】产品应用场景图
- 产品置于真实使用场景中，主体仍然突出
- 场景补充：{scene_text if scene_text else '家居/办公/户外等自然使用环境'}
- 场景元素为陪衬，避免喧宾夺主
""".strip()
    elif image_type == "spec":
        extra = f"""
【画面类型】尺寸规格图
- 生成简洁信息图风格画面
- 展示产品整体及尺寸标注线
- 尺寸信息：{specs_text}
- 数据标注清晰、排版整齐
""".strip()
    else:
        extra = "【画面类型】通用产品图"

    return f"{common}\n\n{extra}".strip()
