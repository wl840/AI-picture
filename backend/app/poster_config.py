from __future__ import annotations

from typing import Dict, List

TEMPLATES: List[Dict] = [
    {
        "key": "festival_promo",
        "name": "节日促销",
        "variants": 8,
        "description": "强视觉冲击，适合促销节点活动",
        "tone": "热烈、吸睛、转化导向",
    },
    {
        "key": "product_showcase",
        "name": "产品展示",
        "variants": 6,
        "description": "突出产品卖点与品牌质感",
        "tone": "专业、清晰、品牌导向",
    },
    {
        "key": "event_push",
        "name": "活动推广",
        "variants": 5,
        "description": "强调时间地点和报名行动",
        "tone": "节奏感强、信息集中",
    },
    {
        "key": "business_clean",
        "name": "商务简约",
        "variants": 4,
        "description": "企业宣传、发布会、官网风格物料",
        "tone": "克制、简洁、可信赖",
    },
    {
        "key": "recruitment",
        "name": "招聘海报",
        "variants": 3,
        "description": "突出岗位优势与企业氛围",
        "tone": "年轻、明确、吸引人才",
    },
    {
        "key": "brand_story",
        "name": "品牌宣传",
        "variants": 6,
        "description": "品牌理念、故事和价值传达",
        "tone": "高级、叙事、情感连接",
    },
]

STYLES = [
    {
        "key": "american_impasto",
        "name": "美漫厚涂风",
        "prompt_description": "american comic impasto painting style, thick paint buildup, visible aggressive brush strokes, dramatic chiaroscuro, strong saturated primaries with deep shadow blocks, dynamic heroic perspective, bold contour emphasis, high-impact action poster energy, texture-rich finish; avoid watercolor softness and minimalist flat layout",
    },
    {
        "key": "paper_cut_3d",
        "name": "立体纸雕风",
        "prompt_description": "3d papercraft diorama style, layered paper sheets and cutout geometry, clean contour edges, step-like depth separation, handcrafted matte paper texture, soft cast shadows between layers, structured composition with sculptural rhythm, poetic storybook atmosphere inspired by The Little Prince; avoid glossy plastic reflections and painterly brush texture",
    },
    {
        "key": "pop_american_comic",
        "name": "波普美漫风",
        "prompt_description": "pop american comic style, ultra high-saturation color contrast, halftone texture accents, graphic panel-like visual rhythm, kinetic framing, punchy highlights, contemporary superhero-movie energy similar to spider-verse aesthetics, loud and youthful street attitude; avoid muted palettes and traditional ink wash mood",
    },
    {
        "key": "gongbi_rich_color",
        "name": "工笔重彩风",
        "prompt_description": "traditional chinese gongbi heavy-color style, ultra fine line precision, meticulous detailing, rich mineral-like pigments, ornate classical composition, elegant decorative motifs, layered luxurious color fields, refined eastern court-painting temperament, balanced grandeur and delicacy; avoid rough sketch strokes and western comic rendering",
    },
    {
        "key": "wool_felt_stop_motion",
        "name": "羊毛毡定格",
        "prompt_description": "wool felt stop-motion style, handmade fiber surfaces, soft fuzzy tactile texture, stitched and handmade micro-imperfections, warm miniature set lighting, cozy healing atmosphere, handcrafted puppet-like forms, gentle depth cues, artisanal storytelling charm; avoid hard metallic sheen and sharp digital vector look",
    },
    {
        "key": "extreme_bw_cinema",
        "name": "极致黑白风格",
        "prompt_description": "extreme black and white cinematic style, pure monochrome palette, ultra-strong tonal contrast, deep noir shadows, controlled hard highlights, premium film-grain photography feel, dramatic narrative framing, high-end editorial poster mood; strictly avoid any visible color tint or candy-style saturation",
    },
    {
        "key": "clay_stop_motion",
        "name": "黏土定格",
        "prompt_description": "clay stop-motion style, sculpted clay materials with finger-molded traces, retro quirky character proportions, playful and slightly eerie handcrafted mood, miniature practical set lighting, tactile matte surfaces, whimsical dark-fairy-tale charm reminiscent of coraline-like stop-motion; avoid smooth realistic skin rendering and 2d anime lineart",
    },
    {
        "key": "neo_chinese_ink",
        "name": "新中式水墨风",
        "prompt_description": "neo chinese ink wash style, flowing ink diffusion and wet-on-wet gradients, elegant blank-space composition, poetic xieyi atmosphere, soft mist layering, restrained accent colors over grayscale base, modern eastern minimalism fused with classical brush spirit, airy and expressive rhythm; avoid neon cyber glow and dense comic halftone texture",
    },
    {
        "key": "ghibli_watercolor",
        "name": "吉卜力风",
        "prompt_description": "ghibli-inspired hand-painted watercolor animation style, warm natural sunlight, rich environmental storytelling, gentle wind-and-nature atmosphere, delicate emotional expression, layered scenic details, soft cinematic framing, healing pastoral tone, high-quality traditional animation background aesthetics; avoid harsh sci-fi neon contrast and heavy noir shadows",
    },
    {
        "key": "cute_3d_toon",
        "name": "3D萌版",
        "prompt_description": "cute 3d toon animation style, stylized adorable proportions, high-quality pbr materials, soft global illumination, smooth rounded geometry, realistic yet gentle material rendering, polished skin and fabric response, bright friendly palette, premium family-oriented cg film quality; avoid flat 2d brushstroke textures and gritty realism",
    },
]

STYLE_MAP = {s["key"]: s for s in STYLES}

ASPECT_RATIOS: Dict[str, Dict] = {
    "square": {"label": "朋友圈", "size": "1024x1024", "ratio": "1:1"},
    "mobile": {"label": "手机竖版", "size": "1024x1792", "ratio": "9:16"},
    "landscape": {"label": "横版海报", "size": "1792x1024", "ratio": "16:9"},
}

