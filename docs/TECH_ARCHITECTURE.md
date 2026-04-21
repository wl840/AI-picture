# AI Picture 项目技术架构文档

> 文档目的：系统化梳理当前仓库的技术架构、模块职责、核心调用链和可扩展点，作为开发、联调、排障与后续重构依据。

## 1. 项目概览

AI Picture 是一个前后端分离的 AI 视觉生成系统，围绕电商营销素材提供四类核心能力：

1. 单张海报生成（Poster）
2. 商品五图生成（Product Set）
3. 漫画分镜与漫画条生成（Comic）
4. 图像后处理（本地叠加 / AI 编辑）

系统总体采用：

- 前端：React + Vite（单页应用，Hash 路由）
- 后端：FastAPI（服务编排 + 文件存储 + 记录管理）
- 上游模型：DashScope / OpenAI 兼容图像接口（统一由 `ImageProviderService` 路由）

---

## 2. 总体架构

```text
[Frontend React]
   ├─ GeneratorPage（海报/五图/漫画）
   └─ PostprocessPage（后处理）
          |
          v
[FastAPI API Layer: app/main.py]
   ├─ PosterService
   ├─ ProductSetService
   ├─ ComicService + ComicTaskService
   ├─ PostprocessService
   ├─ StorageService
   └─ ImageRecordService
          |
          v
[ImageProviderService]
   ├─ DashScope 多模态图像接口
   └─ OpenAI-compatible /responses 或 /images/generations

[本地文件系统]
   ├─ backend/app/uploads（用户上传）
   ├─ backend/app/data（生成结果）
   └─ backend/app/data/image_records.json（图片记录）
```

---

## 3. 目录与模块

## 3.1 后端目录

- `backend/app/main.py`：API 入口、路由与静态文件挂载
- `backend/app/schemas.py`：Pydantic 请求/响应模型与校验规则
- `backend/app/poster_config.py`：模板、风格、比例等配置
- `backend/app/prompt_engineering.py`：海报/五图/漫画分镜 prompt 生成
- `backend/app/services/`
  - `image_provider.py`：统一上游模型调用网关
  - `poster_service.py`：海报业务编排
  - `product_set_service.py`：五图业务编排
  - `comic_prompt_service.py`：漫画结构化分镜与台词生成（LLM）
  - `comic_service.py`：漫画逐格生图 + 合成长图
  - `comic_task_service.py`：漫画异步任务管理（内存）
  - `postprocess_service.py`：后处理（本地叠加 / AI）
  - `storage.py`：Logo/产品图上传存储与 DataURL 转换
  - `image_record_service.py`：生成记录登记、查询、软删除
  - `image_postprocess.py`：固定 Logo 贴图（自适应底框）

## 3.2 前端目录

- `frontend/src/App.jsx`：顶层导航与页面切换
- `frontend/src/api.js`：所有后端 API 封装
- `frontend/src/pages/GeneratorPage.jsx`：生成页（海报/五图/漫画）
- `frontend/src/pages/PostprocessPage.jsx`：后处理页
- `frontend/src/components/ImageLightbox.jsx`：全局图片点击放大预览
- `frontend/src/styles/app.css`：全局样式

---

## 4. 后端架构详解

## 4.1 API 层（`main.py`）

职责：

1. 注册业务接口
2. 参数与响应模型约束（由 `schemas.py` 提供）
3. 静态资源挂载
   - `/static/generated` -> `backend/app/data`
   - `/static/uploads` -> `backend/app/uploads`
4. CORS 放开（当前为 `*`）

接口分组：

- 配置与健康：`/health`、`/api/poster/options`
- 上传：`/api/poster/upload-logo`、`/api/product/upload-image`
- 生成：`/api/poster/generate`、`/api/product/generate-set`、`/api/poster/generate-comic`
- 漫画任务：`/api/poster/generate-comic/task`（创建/查询）
- 后处理：`/api/poster/postprocess`
- 记录管理：`/api/poster/generated-images`、`/api/poster/image-records` 及删除接口

## 4.2 统一模型网关（`ImageProviderService`）

核心特性：

1. 根据 `model + base_url` 自动分流
   - DashScope 分支
   - OpenAI-compatible 分支
2. 自动拼装不同上游 payload
   - DashScope：`input.messages[].content=[image..., text]`
   - OpenAI-compatible：
     - 带参考图 -> `/responses` + `image_generation tool`
     - 无参考图 -> `/images/generations`
3. 统一结果解析
   - URL
   - Base64
   - 多种返回结构兼容
4. 统一异常包装
   - 上游状态码
   - request_id
   - 截断后的响应体

这使业务服务不关心具体服务商协议，只调用 `generate_image(...)`。

## 4.3 业务服务层

### 4.3.1 `PosterService`

流程：

1. 构建海报 prompt（模板+风格+产品）
2. 调用统一生图
3. 解析落地本地文件（URL/Base64 都兼容）
4. 可选固定 Logo 本地贴图（`image_postprocess.py`）
5. 记录写入 `ImageRecordService`

### 4.3.2 `ProductSetService`

流程：

1. 读取产品参考图（上传文件）并转 DataURL
2. 按 5 类图片模板循环生成（主图/细节/卖点/场景/规格）
3. 单项失败不中断全流程
4. 若 5 项全失败则抛错
5. 成功项登记记录

### 4.3.3 `ComicPromptService`

职责：把漫画输入转成结构化分镜语义。

当前实现要点：

1. 使用文本模型（`qwen3.6-plus`）调用 `/chat/completions`
2. 输出强约束 JSON：
   - `visual_prompt`
   - `dialogue`
   - `emotion`
   - `product_focus`
3. 解析失败自动重试（`MAX_RETRIES = 1`）
4. 台词长度限制（<=20 字符）
5. 可选二次台词润色（`model_text` 模式）

### 4.3.4 `ComicService`

职责：漫画主编排器。

流程：

1. 生成剧情草案（storyboard）
2. 调用 `ComicPromptService` 产出结构化分镜
3. 逐格生成图像（可带产品参考图 + 上一格参考图）
4. 汇总每格结果
5. 全部成功后合成漫画条

Prompt 侧特点：

- 统一组装为语义一致格式（画面、对白、情绪、卖点同源）
- 附加“连续性参考图规则”约束

漫画条合成特点（近期改造）：

1. 自动布局候选池（4/6 格）
2. 评分选最优布局（占用率/比例匹配/阅读顺序）
3. `contain + blur` 渲染，减少留白且不裁主体
4. 支持 9:16 与 16:9 输出画布

### 4.3.5 `ComicTaskService`

职责：漫画异步任务管理（前端轮询）。

特点：

1. 内存态任务表 `_tasks`
2. 任务状态：`pending/running/completed/failed`
3. 面板粒度状态：`pending/prompt_ready/done/failed`
4. 通过 `progress_hook` 接收逐格进度

注意：服务重启后任务丢失（无持久化）。

### 4.3.6 `PostprocessService`

支持两种模式：

1. `local`：本地叠加 Logo/水印/文本（不会重绘整图）
2. `ai`：把原图（可带 logo 参考图）交给模型编辑（会重绘整图）

AI 模式当前行为：

- 原图 + logo 作为参考输入
- 通过 prompt 强约束 logo 角落与数量
- 结果仍可能改动对白文字（重绘行为导致）

### 4.3.7 `StorageService`

- 校验上传 MIME 是否图片
- 统一命名保存到 `uploads`
- 提供 `file_to_data_url` 供参考图场景复用

### 4.3.8 `ImageRecordService`

职责：图片记录生命周期管理。

能力：

1. 历史文件回填（seed）
2. 记录登记（来源类型/批次/槽位/meta）
3. 记录查询（可过滤软删除）
4. 软删除（按 record_id 或 path）
5. 兼容 legacy 软删除文件迁移

---

## 5. 前端架构详解

## 5.1 页面组织

1. `GeneratorPage`
   - 海报生成
   - 五图生成
   - 漫画异步任务轮询展示
   - 支持结果下载与 prompt 查看
2. `PostprocessPage`
   - 本地叠加与 AI 编辑切换
   - 图片记录选择、批处理、删除
3. `ImageLightbox`
   - 点击任意结果图放大预览
   - 点击/遮罩/Esc 关闭
   - 打开时锁定 body 滚动

## 5.2 API 访问层

`frontend/src/api.js` 统一管理所有后端接口调用与错误抛出，页面只做状态与视图编排。

---

## 6. 核心调用链（端到端）

## 6.1 海报生成

```text
GeneratorPage -> POST /api/poster/generate
  -> PosterService
    -> build_poster_prompt
    -> ImageProviderService.generate_image
    -> (可选) add_logo_to_image
    -> ImageRecordService.register_saved_image
```

## 6.2 商品五图生成

```text
GeneratorPage -> POST /api/product/generate-set
  -> ProductSetService
    -> 读取产品图 DataURL
    -> 循环 5 类 prompt 生成
    -> 单项容错，汇总返回
    -> 记录入库
```

## 6.3 漫画生成（异步任务）

```text
GeneratorPage -> POST /api/poster/generate-comic/task
  -> ComicTaskService.create_task + asyncio.create_task(run_task)
    -> ComicService.generate_comic
      -> build_comic_storyboard
      -> ComicPromptService.generate_panel_prompts
      -> 逐格 ImageProviderService.generate_image
      -> compose_comic_strip
  -> 前端轮询 GET /api/poster/generate-comic/task/{task_id}
```

## 6.4 后处理

```text
PostprocessPage -> POST /api/poster/postprocess
  -> PostprocessService.postprocess_images
    -> process_mode == local: 本地叠加
    -> process_mode == ai: 上游模型编辑
  -> ImageRecordService.register_saved_image
```

---

## 7. 配置与模型策略

## 7.1 前端环境变量

- `VITE_API_BASE`：后端地址
- `VITE_DEFAULT_API_KEY`：默认 key（本地开发）
- `VITE_IMAGE_BASE_URL`：默认上游网关

## 7.2 默认模型

- 海报/五图：`qwen-image-2.0-pro`
- 漫画生图：`wan2.7-image`
- 漫画分镜 LLM：`qwen3.6-plus`
- 后处理 AI：`qwen-image-edit-max`

## 7.3 文字策略

- 漫画支持 `text_mode`：
  - `post_render`：只保留空白气泡，不让模型写字
  - `model_text`：允许模型写对白（当前前端默认）

---

## 8. 存储与文件模型

## 8.1 文件目录

- `backend/app/uploads`：用户上传原始图（logo、产品参考图）
- `backend/app/data`：模型输出和后处理结果

## 8.2 记录文件

- `image_records.json`：主记录
- `generated_images_soft_deleted.json`：legacy 软删迁移来源

---

## 9. 当前架构优点

1. 业务编排与模型协议解耦（统一网关）
2. 单项任务容错能力较好（五图、漫画逐格）
3. 漫画链路已具备“结构化分镜 + 连续性参考图 + 自动拼条”
4. 前端交互完整（任务进度、下载、放大预览、记录管理）

---

## 10. 当前风险与限制

1. 漫画任务仅内存态，服务重启任务丢失
2. 后处理 `ai` 模式会重绘整图，可能改变对话框文字
3. CORS 全开放且无鉴权，不适合直接公网暴露
4. 文件存储与记录为本地磁盘/JSON，单机可用，扩展性一般
5. 缺少队列与限流，峰值场景可能阻塞

---

## 11. 建议的演进方向

1. 任务持久化：引入 Redis + 任务队列（RQ/Celery/Arq）
2. 存储升级：对象存储（OSS/S3）+ 元数据数据库
3. 安全与治理：鉴权、配额、审计日志、速率限制
4. 后处理安全模式：`ai_logo_safe`（logo-only AI + 本地合成，保证对白不变）
5. 观测性：结构化日志、请求链路 ID、错误分类告警

---

## 12. 快速阅读索引（关键文件）

- 后端入口：[main.py](/d:/桌面/AI%20picture01/backend/app/main.py)
- 协议模型：[schemas.py](/d:/桌面/AI%20picture01/backend/app/schemas.py)
- 模型网关：[image_provider.py](/d:/桌面/AI%20picture01/backend/app/services/image_provider.py)
- 漫画主流程：[comic_service.py](/d:/桌面/AI%20picture01/backend/app/services/comic_service.py)
- 漫画结构化分镜：[comic_prompt_service.py](/d:/桌面/AI%20picture01/backend/app/services/comic_prompt_service.py)
- 后处理流程：[postprocess_service.py](/d:/桌面/AI%20picture01/backend/app/services/postprocess_service.py)
- 图片记录：[image_record_service.py](/d:/桌面/AI%20picture01/backend/app/services/image_record_service.py)
- 前端 API：[api.js](/d:/桌面/AI%20picture01/frontend/src/api.js)
- 生成页：[GeneratorPage.jsx](/d:/桌面/AI%20picture01/frontend/src/pages/GeneratorPage.jsx)
- 后处理页：[PostprocessPage.jsx](/d:/桌面/AI%20picture01/frontend/src/pages/PostprocessPage.jsx)

