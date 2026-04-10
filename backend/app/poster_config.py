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
    "简约商务",
    "活力时尚",
    "中国风",
    "科技感",
    "文艺清新",
    "高端大气",
]

ASPECT_RATIOS: Dict[str, Dict] = {
    "square": {"label": "朋友圈", "size": "1024x1024"},
    "mobile": {"label": "手机竖版", "size": "1024x1792"},
    "landscape": {"label": "横版海报", "size": "1792x1024"},
}
