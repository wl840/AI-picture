from __future__ import annotations

from typing import List, Optional

from .poster_config import ASPECT_RATIOS, TEMPLATES


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


def build_prompt(
    product_name: str,
    style: str,
    position: str,
    logo_mode: str,
    *,
    highlights_text: str = "",
    description_text: str = "",
    ratio_label: str = "方形",
    ratio_size: str = "1024x1024",
    logo_filename: Optional[str] = None,
) -> str:
    """
    通用商品海报 Prompt：
    - fixed：产品图优先，禁止模板化结构，并预留 logo 区域
    - ai：允许 logo 融合，但强约束 logo 不可变形/重绘
    """
    base = f"""
设计一张电商产品海报。

【产品主体】
产品是：{product_name}
必须生成该产品的真实视觉形象（写实风格）

【核心要求】
1. 产品必须清晰可见，并作为画面主体
2. 产品占据视觉中心
3. 产品细节清晰（材质、结构、光影）

【风格】
- {style}
- 商业广告质感
- 干净背景

【布局】
- 中间：产品主体
- 上方：标题
- 下方：辅助文案

【禁止】
- 不要生成无关字符或标识
- 不要生成信息卡片
- 不要出现“产品名称”“CTA”“占位文本”
- 不要模板结构
- 不要只有文字


【补充信息】
- 比例：{ratio_label}（{ratio_size}）
- 卖点：{highlights_text if highlights_text else '无'}
- 描述：{description_text if description_text else '无'}
""".strip()

    if logo_mode == "fixed":
        # fixed 模式：模型不处理 logo，只预留留白。
        return (
            base
            + f"""

【Logo】
请在{position}预留空白区域用于放置logo
不要在该区域生成任何图形或文字
不要生成任何品牌图标、徽章、占位框
"""
        ).strip()

    # ai 模式：允许融合 logo，但严格约束 logo 真实性。
    return (
        base
        + f"""

【Logo】
已提供品牌logo参考图（{logo_filename or '上传的logo图片'}）
必须使用提供logo，保持原始形状与比例
不要重新设计logo，不要生成假logo
不要生成占位框、边框、替代图标
logo应自然融入画面，但不得遮挡产品主体
"""
    ).strip()


def build_poster_prompt(
    *,
    template_key: str,
    product_name: str,
    highlights: List[str],
    style: str,
    description: Optional[str],
    ratio_key: str,
    logo_mode: str,
    logo_position: Optional[str],
    logo_filename: Optional[str] = None,
) -> str:
    """兼容现有调用，内部转发到新 build_prompt。"""
    template = _template_meta(template_key)
    ratio = ASPECT_RATIOS.get(ratio_key, ASPECT_RATIOS["square"])
    highlights_text = _join_highlights(highlights)
    description_text = description.strip() if description else ""

    # 把模板语气融入 style，避免额外模板化字样进入输出。
    merged_style = f"{style}，{template['tone']}"

    return build_prompt(
        product_name=product_name,
        style=merged_style,
        position=_position_label(logo_position),
        logo_mode=logo_mode,
        highlights_text=highlights_text,
        description_text=description_text,
        ratio_label=ratio["label"],
        ratio_size=ratio["size"],
        logo_filename=logo_filename,
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
- 风格：{style}
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
