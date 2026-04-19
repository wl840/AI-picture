# AI Picture

一个前后端分离的 AI 海报生成项目：
- 前端（React + Vite）负责参数配置、Logo 上传、结果预览与下载
- 后端（FastAPI）负责 Prompt 生成、调用图像模型、Logo 后处理与静态资源托管

支持两种 Logo 模式：
- `fixed`：模型先出主图，后端再把 Logo 稳定贴到指定角落（推荐）
- `ai`：把 Logo 作为参考图交给模型融合

## 功能概览

- 模板化海报场景（节日促销、产品展示、活动推广等）
- 风格选择、比例选择（1:1 / 9:16 / 16:9）
- 品牌 Logo 上传与位置控制
- 返回可直接访问的图片 URL（同时兼容 base64 返回）
- 前端一键预览和下载

## 技术栈

- Frontend: React 18, Vite 5
- Backend: FastAPI, Uvicorn, Pydantic v2, httpx, Pillow
- Image Provider: DashScope（Qwen）或 OpenAI 兼容接口

## 目录结构

```text
AI picture/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                  # FastAPI 入口
│  │  ├─ prompt_engineering.py    # Prompt 拼装
│  │  ├─ poster_config.py         # 模板/风格/比例配置
│  │  ├─ services/
│  │  │  ├─ image_provider.py     # 调用上游图像模型
│  │  │  ├─ image_postprocess.py  # fixed 模式 Logo 贴图
│  │  │  ├─ poster_service.py     # 生成流程编排
│  │  │  └─ storage.py            # Logo 存储
│  │  ├─ data/                    # 生成图片输出目录（运行时创建）
│  │  └─ uploads/                 # Logo 上传目录
│  └─ requirements.txt
└─ frontend/
   ├─ src/App.jsx                 # 页面主逻辑
   ├─ src/api.js                  # 前端 API 封装
   └─ package.json
```

## 快速开始

### 1) 启动后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端默认地址：`http://127.0.0.1:8000`

### 2) 启动前端

另开一个终端：

```powershell
cd frontend
npm install
npm run dev
```

前端默认地址：`http://127.0.0.1:5173`

## 前端环境变量（可选）

在 `frontend/.env` 中可配置：

```env
VITE_API_BASE=http://127.0.0.1:8000
VITE_DEFAULT_API_KEY=你的API_KEY
VITE_IMAGE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

说明：
- `VITE_API_BASE`：前端请求后端的基础地址
- `VITE_DEFAULT_API_KEY`：页面默认填充 API Key（仅本地开发建议）
- `VITE_IMAGE_BASE_URL`：后端请求的模型网关地址（与所用模型匹配）

## 使用流程

1. 打开前端页面，选择模板、风格和比例
2. 填写产品/活动名称、卖点、补充描述
3. （可选）上传 Logo，选择 `fixed` 或 `ai` 模式
4. 点击“AI 生成海报”
5. 在预览区查看结果并下载

## API 一览

### `GET /health`

健康检查：

```json
{ "status": "ok" }
```

### `GET /api/poster/options`

返回模板、风格、比例配置：

```json
{
  "templates": [],
  "styles": [],
  "aspect_ratios": {}
}
```

### `POST /api/poster/upload-logo`

`multipart/form-data` 上传字段：`file`

响应示例：

```json
{
  "logo_id": "2fa4...c3b",
  "filename": "2fa4...c3b.png",
  "url": "/static/uploads/2fa4...c3b.png"
}
```

### `POST /api/poster/generate`

请求示例：

```json
{
  "api_key": "sk-xxxx",
  "model": "qwen-image-2.0-pro",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "template_key": "festival_promo",
  "style": "简约商务",
  "ratio_key": "square",
  "product_name": "夏季轻薄防晒衣",
  "highlights": ["UPF50+", "透气速干"],
  "description": "主打户外通勤与城市骑行",
  "logo_id": "2fa4...c3b",
  "logo_mode": "fixed",
  "logo_position": "top_right"
}
```

响应示例：

```json
{
  "image_url": null,
  "image_base64": null,
  "saved_path": "/static/generated/generated_fixed_logo_xxx.png",
  "prompt": "..."
}
```

## Logo 模式说明

- `fixed`（推荐）：
  - 不把 Logo 交给模型重绘
  - 模型只生成主视觉，后端用 Pillow 贴图
  - 稳定、可控、品牌一致性高
- `ai`：
  - Logo 作为参考图传给模型融合
  - 效果更自由，但一致性受模型波动影响

## 输出与静态资源

- 生成海报目录：`backend/app/data`
- 上传 Logo 目录：`backend/app/uploads`
- 访问路径：
  - `/static/generated/...`
  - `/static/uploads/...`

## 常见问题

- `请在 frontend/.env 中配置 VITE_DEFAULT_API_KEY`
  - 这是前端校验提示，补上 `VITE_DEFAULT_API_KEY` 或在界面输入有效 key。
- 上游返回 4xx/5xx
  - 检查 `api_key`、`model`、`base_url` 是否匹配同一服务商。
- CORS/跨域问题
  - 后端当前已放开 `allow_origins=["*"]`，本地开发默认可直接联调。

## 开发建议

- 不要把真实 API Key 提交到仓库
- `frontend/.vite/`、`backend/app/data/`、上传文件都属于本地运行产物
- 若需生产部署，建议增加鉴权、限流、日志脱敏与对象存储
