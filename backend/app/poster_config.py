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
        "description": "企业宣传、发布会、官网风物料",
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
        "tone": "高级、叙事、情感链接",
    },
]

STYLES = [
    {
        "key": "american_comic",
        "name": "美漫厚涂风",
        "prompt_description": "美式超级英雄漫画风格，粗犷的墨线轮廓，厚重的不透明颜料平涂，对比强烈的深色阴影，鲜艳的原色系配色，充满力量感的动感构图，漫威/DC漫画质感",
    },
    {
        "key": "ghibli",
        "name": "吉卜力风格",
        "prompt_description": "宫崎骏吉卜力手绘动画风格，柔和的水彩质感，细腻丰富的背景细节，温暖的马卡龙配色，圆润可爱的角色造型，充满梦幻田园气息",
    },
    {
        "key": "cel_anime",
        "name": "赛璐璐动漫风",
        "prompt_description": "90年代日系赛璐璐动画风格，干净锐利的线条，大面积平涂色块，富有表现力的大眼睛，有限色阶的简洁阴影，少年漫画视觉语言",
    },
    {
        "key": "cyberpunk_neon",
        "name": "赛博朋克霓虹",
        "prompt_description": "赛博朋克霓虹都市插画，雨后湿润的反光街道，电气感的洋红和青色霓虹灯光，密集的城市层次，金属质感，数字故障效果，银翼杀手和攻壳机动队视觉风格",
    },
    {
        "key": "ink_animation",
        "name": "水墨动画风",
        "prompt_description": "中国传统水墨动画风格，流动的水墨笔触，大量留白构图，墨色浓淡变化，偶尔点缀朱红色，诗意山水意境，写意笔法",
    },
    {
        "key": "pixel_retro",
        "name": "像素复古游戏",
        "prompt_description": "复古16位像素游戏风格，等距或横版卷轴视角，色彩抖动阴影，限定32色调色板，可见像素格的方块化精灵图，90年代JRPG平台游戏美学",
    },
    {
        "key": "fairy_tale",
        "name": "欧式童话插画",
        "prompt_description": "欧洲童话故事书插画，细密的钢笔线条配合水彩渲染，华丽的装饰边框，温暖烛光般的琥珀色调，黄金时代插画风格，精致唯美",
    },
    {
        "key": "steampunk",
        "name": "蒸汽朋克机械",
        "prompt_description": "蒸汽朋克机械插画，蚀刻铜制齿轮和管道纹理，维多利亚时代版画风格，可见铆钉细节，蒸汽光源下的强烈明暗对比，复古未来主义",
    },
    {
        "key": "flat_illustration",
        "name": "扁平插画风",
        "prompt_description": "现代扁平设计插画，几何简化造型，大色块对比配色，无投影无纹理，北欧简约海报美学，干净清爽的视觉语言",
    },
    {
        "key": "dark_gothic",
        "name": "暗黑哥特风",
        "prompt_description": "暗黑哥特奇幻插画，戏剧性烛光明暗对比，深宝石色调（深红与紫罗兰），哥特教堂和乌鸦元素，细密交叉排线纹理，蒂姆伯顿视觉美学",
    },
]

STYLE_MAP = {s["key"]: s for s in STYLES}

ASPECT_RATIOS: Dict[str, Dict] = {
    "square": {"label": "朋友圈", "size": "1024x1024"},
    "mobile": {"label": "手机竖版", "size": "1024x1792"},
    "landscape": {"label": "横版海报", "size": "1792x1024"},
}
