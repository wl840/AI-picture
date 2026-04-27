import { useEffect, useMemo, useState } from "react";
import {
  deleteGeneratedImage,
  deleteImageRecord,
  fetchImageRecords,
  postprocessImages,
  toAbsoluteUrl,
  uploadLogo,
  uploadQrImage,
} from "../api";
import ImageLightbox from "../components/ImageLightbox";

const DEFAULT_IMAGE_BASE_URL =
  import.meta.env.VITE_IMAGE_BASE_URL ||
  "https://dashscope.aliyuncs.com/api/v1";

const initialForm = {
  processMode: "local",
  useLogo: true,
  logoPosition: "bottom_right",
  watermarkText: "",
  watermarkPosition: "bottom_right",
  textContent: "",
  textPosition: "top_left",
  useQrCard: false,
  qrPosition: "bottom_right",
  qrScale: 0.18,
  qrPhoneNumber: "",
  apiKey: import.meta.env.VITE_DEFAULT_API_KEY || "",
  model: "wan2.7-image-pro",
  baseUrl: DEFAULT_IMAGE_BASE_URL,
  aiPrompt: `【任务目标】
将提供的logo自然融合到画面中，而不是作为叠加元素

【融合方式】
让logo成为场景中的一部分（diegetic design），可以以如下形式存在：
- 环境装饰（墙面雕刻 / 招牌 / 标识）
- 物体表面（服装刺绣 / 包装印刷 / 地面纹样）
- 材质融合（金属浮雕 / 烫金 / 压印 / 光影投影）

【风格一致性】
保持logo与整体画面风格一致：
- 色彩匹配（与环境主色调统一）
- 线条风格统一（插画 / 写实 / 扁平）
- 细节复杂度一致

【光影与空间】
- 使用与场景一致的光源方向和强度
- 添加真实阴影、高光和环境反射
- 符合透视关系和空间结构

【构图要求】
- 不要单独留白区域放logo
- 不要居中悬浮或底部贴图
- logo应自然出现在视觉路径中（如背景/中景元素）

【质感要求】
- 增加真实材质表现（纹理、磨损、凹凸）
- 避免“贴纸感”“UI叠加感”

【质量目标】
整体效果应呈现：
- seamless integration（无缝融合）
- natural blending（自然融合）
- high-end commercial quality（高级商业感）

【负面约束】
避免：
- logo悬浮 / 贴图感 / 拼贴感
- 独立白底logo区域
- 风格不统一
- 过高对比导致突兀`,
  aiRatioKey: "square",
  aiLayoutMode: "auto",
  aiTitleText: "",
  aiCtaText: "",
};

function PostprocessPage() {
  const [form, setForm] = useState(initialForm);
  const [images, setImages] = useState([]);
  const [selectedPaths, setSelectedPaths] = useState([]);
  const [logoInfo, setLogoInfo] = useState(null);
  const [qrInfo, setQrInfo] = useState(null);
  const [loadingList, setLoadingList] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [deletingKey, setDeletingKey] = useState("");
  const [lightbox, setLightbox] = useState({ open: false, src: "", alt: "" });

  const selectedSet = useMemo(() => new Set(selectedPaths), [selectedPaths]);

  const updateField = (name, value) => {
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const loadImages = async () => {
    setLoadingList(true);
    setError("");
    try {
      const list = await fetchImageRecords();
      const nextImages = list || [];
      setImages(nextImages);
      const visiblePathSet = new Set(nextImages.map((item) => item.path));
      setSelectedPaths((prev) => prev.filter((path) => visiblePathSet.has(path)));
    } catch (err) {
      setError(err.message || "加载图片列表失败");
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => {
    loadImages();
  }, []);

  const onUploadLogo = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    try {
      const uploaded = await uploadLogo(file);
      setLogoInfo(uploaded);
      setMessage(`Logo 已上传：${uploaded.filename}`);
    } catch (err) {
      setError(err.message || "Logo 上传失败");
    }
  };

  const onUploadQr = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    try {
      const uploaded = await uploadQrImage(file);
      setQrInfo(uploaded);
      setMessage(`二维码已上传：${uploaded.filename}`);
    } catch (err) {
      setError(err.message || "二维码上传失败");
    }
  };

  const togglePath = (path) => {
    setSelectedPaths((prev) => {
      if (prev.includes(path)) return prev.filter((item) => item !== path);
      return [...prev, path];
    });
  };

  const selectAll = () => {
    setSelectedPaths(images.map((item) => item.path));
  };

  const clearSelection = () => {
    setSelectedPaths([]);
  };

  const openLightbox = (src, alt) => {
    if (!src) return;
    setLightbox({ open: true, src, alt: alt || "" });
  };

  const closeLightbox = () => {
    setLightbox({ open: false, src: "", alt: "" });
  };

  const onDeleteImage = async (item) => {
    const confirmed = window.confirm("确认删除这张图片记录吗？删除仅做标记，不会物理删除文件。");
    if (!confirmed) return;

    const deleteKey = item.record_id || item.path;
    setDeletingKey(deleteKey);
    setError("");
    setMessage("");
    try {
      if (item.record_id) {
        await deleteImageRecord(item.record_id);
      } else {
        await deleteGeneratedImage(item.path);
      }
      setImages((prev) => prev.filter((row) => (row.record_id || row.path) !== deleteKey));
      setSelectedPaths((prev) => prev.filter((itemPath) => itemPath !== item.path));
      setMessage("删除成功");
    } catch (err) {
      setError(err.message || "删除失败");
      setMessage("删除失败");
    } finally {
      setDeletingKey("");
    }
  };

  const runPostprocess = async () => {
    if (!selectedPaths.length) {
      setError("请先选择要处理的图片。");
      return;
    }

    const hasLogo = form.useLogo && !!logoInfo?.logo_id;
    const hasQrCard = form.useQrCard && !!qrInfo?.qr_id;
    if (form.processMode === "local" && !hasLogo && !form.watermarkText.trim() && !form.textContent.trim() && !hasQrCard) {
      setError("本地模式下请至少启用一项：Logo、水印、文字或二维码卡片。");
      return;
    }

    if (form.processMode === "local" && form.useQrCard && !hasQrCard) {
      setError("已启用二维码卡片，请先上传二维码图片。");
      return;
    }

    if (form.processMode === "ai" && !form.apiKey.trim()) {
      setError("AI 模式需要 API Key。");
      return;
    }
    if (form.processMode === "ai" && form.useQrCard && !hasQrCard) {
      setError("AI 模式已启用二维码信息区，请先上传二维码图片。");
      return;
    }

    setProcessing(true);
    setError("");
    setMessage("");
    try {
      const result = await postprocessImages({
        image_paths: selectedPaths,
        process_mode: form.processMode,
        logo_id: hasLogo ? logoInfo.logo_id : null,
        logo_position: form.logoPosition,
        watermark_text: form.watermarkText.trim(),
        watermark_position: form.watermarkPosition,
        text_content: form.textContent.trim(),
        text_position: form.textPosition,
        qr_enabled: form.useQrCard,
        qr_image_id: hasQrCard ? qrInfo.qr_id : null,
        qr_position: form.qrPosition,
        qr_scale: Number(form.qrScale) || 0.18,
        phone_number: form.qrPhoneNumber.trim(),
        api_key: form.apiKey.trim(),
        model: form.model.trim(),
        base_url: form.baseUrl.trim(),
        ai_prompt: form.aiPrompt.trim(),
        ai_ratio_key: form.aiRatioKey,
        ai_layout_mode: form.aiLayoutMode,
        ai_title_text: form.aiTitleText.trim(),
        ai_cta_text: form.aiCtaText.trim(),
      });

      const success = result?.success_count || 0;
      const failed = (result?.items || []).filter((entry) => entry.error).length;
      setMessage(`处理完成：成功 ${success} 张，失败 ${failed} 张。`);

      await loadImages();
      const newPaths = (result?.items || []).map((entry) => entry.saved_path).filter(Boolean);
      setSelectedPaths(newPaths);
    } catch (err) {
      setError(err.message || "后处理失败");
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="page-wrap">
      <main className="board postprocess-board">
        <section className="panel form-panel">
          <h1>后处理中心</h1>

          <div className="section">
            <h2>处理模式</h2>
            <div className="chips">
              {[
                { key: "local", name: "本地叠加" },
                { key: "ai", name: "AI 编辑模型" },
              ].map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`chip ${form.processMode === item.key ? "active" : ""}`}
                  onClick={() => updateField("processMode", item.key)}
                >
                  {item.name}
                </button>
              ))}
            </div>
          </div>

          <div className="section">
            <h2>Logo 参考图</h2>
            <div className="form-group">
              <label style={{ gridColumn: "1 / -1", flexDirection: "row", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={form.useLogo}
                  onChange={(e) => updateField("useLogo", e.target.checked)}
                />
                使用 logo 参考图（本地叠加和 AI 模式都可用）
              </label>

              <select value={form.logoPosition} onChange={(e) => updateField("logoPosition", e.target.value)}>
                <option value="top_left">Logo：左上角</option>
                <option value="top_right">Logo：右上角</option>
                <option value="bottom_left">Logo：左下角</option>
                <option value="bottom_right">Logo：右下角</option>
              </select>

              <input type="file" accept="image/*" onChange={onUploadLogo} />
            </div>
            <p className="tip">{logoInfo ? `已上传：${logoInfo.filename}` : "未上传 logo（可选）"}</p>
          </div>

          {form.processMode === "local" ? (
            <>
              <div className="section">
                <h2>本地叠加参数</h2>
                <div className="form-group">
                  <input
                    type="text"
                    placeholder="水印文字（可选）"
                    value={form.watermarkText}
                    onChange={(e) => updateField("watermarkText", e.target.value)}
                  />

                  <select value={form.watermarkPosition} onChange={(e) => updateField("watermarkPosition", e.target.value)}>
                    <option value="top_left">水印：左上角</option>
                    <option value="top_right">水印：右上角</option>
                    <option value="bottom_left">水印：左下角</option>
                    <option value="bottom_right">水印：右下角</option>
                    <option value="center">水印：居中</option>
                  </select>

                  <input
                    type="text"
                    placeholder="自定义文字（可选）"
                    value={form.textContent}
                    onChange={(e) => updateField("textContent", e.target.value)}
                  />

                  <select value={form.textPosition} onChange={(e) => updateField("textPosition", e.target.value)}>
                    <option value="top_left">文字：左上角</option>
                    <option value="top_right">文字：右上角</option>
                    <option value="bottom_left">文字：左下角</option>
                    <option value="bottom_right">文字：右下角</option>
                    <option value="center">文字：居中</option>
                  </select>
                </div>
              </div>

              <div className="section">
                <h2>二维码与联系热线</h2>
                <div className="form-group">
                  <label style={{ gridColumn: "1 / -1", flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={form.useQrCard}
                      onChange={(e) => updateField("useQrCard", e.target.checked)}
                    />
                    启用二维码信息区
                  </label>

                  <select value={form.qrPosition} onChange={(e) => updateField("qrPosition", e.target.value)}>
                    <option value="bottom_left">二维码卡片：左下角</option>
                    <option value="bottom_right">二维码卡片：右下角</option>
                  </select>

                  <input type="file" accept="image/*" onChange={onUploadQr} />

                  <input
                    type="text"
                    placeholder="电话（可选，如 18720155555）"
                    value={form.qrPhoneNumber}
                    onChange={(e) => updateField("qrPhoneNumber", e.target.value)}
                  />

                  <label style={{ gridColumn: "1 / -1" }}>
                    二维码卡片尺寸：{Math.round((Number(form.qrScale) || 0.18) * 100)}%
                    <input
                      type="range"
                      min="0.08"
                      max="0.35"
                      step="0.01"
                      value={form.qrScale}
                      onChange={(e) => updateField("qrScale", Number(e.target.value))}
                    />
                  </label>
                </div>
                <p className="tip">{qrInfo ? `二维码已上传：${qrInfo.filename}` : "未上传二维码（可选）"}</p>
              </div>
            </>
          ) : (
            <>
              <div className="section">
                <h2>AI 编辑参数</h2>
                <div className="form-group">
                  <input
                    type="password"
                    placeholder="API Key"
                    value={form.apiKey}
                    onChange={(e) => updateField("apiKey", e.target.value)}
                  />

                  <input
                    type="text"
                    placeholder="模型名（如 wan2.7-image-pro）"
                    value={form.model}
                    onChange={(e) => updateField("model", e.target.value)}
                  />

                  <input
                    type="text"
                    placeholder="Base URL"
                    value={form.baseUrl}
                    onChange={(e) => updateField("baseUrl", e.target.value)}
                  />

                <select value={form.aiRatioKey} onChange={(e) => updateField("aiRatioKey", e.target.value)}>
                  <option value="square">1:1</option>
                  <option value="mobile">9:16</option>
                  <option value="landscape">16:9</option>
                </select>

                <select value={form.aiLayoutMode} onChange={(e) => updateField("aiLayoutMode", e.target.value)}>
                  <option value="auto">版式识别：自动</option>
                  <option value="single">版式识别：单张海报</option>
                  <option value="comic_4">版式识别：四格漫画</option>
                  <option value="comic_6">版式识别：六格漫画</option>
                </select>

                <input
                  type="text"
                  placeholder="顶部标题（可选）"
                  value={form.aiTitleText}
                  onChange={(e) => updateField("aiTitleText", e.target.value)}
                />

                <input
                  type="text"
                  placeholder="底部引导语（可选）"
                  value={form.aiCtaText}
                  onChange={(e) => updateField("aiCtaText", e.target.value)}
                />

                <textarea
                  placeholder="AI 编辑提示词"
                  value={form.aiPrompt}
                  onChange={(e) => updateField("aiPrompt", e.target.value)}
                />
              </div>
              <p className="tip">AI 模式会自动保护原始核心画面，仅在品牌区融合处理（支持单图/四格/六格）。</p>
            </div>

              <div className="section">
                <h2>AI 模式：二维码与联系热线</h2>
                <div className="form-group">
                  <label style={{ gridColumn: "1 / -1", flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={form.useQrCard}
                      onChange={(e) => updateField("useQrCard", e.target.checked)}
                    />
                    启用二维码信息区（AI 生成后叠加）
                  </label>

                  <select value={form.qrPosition} onChange={(e) => updateField("qrPosition", e.target.value)}>
                    <option value="bottom_left">二维码卡片：左下角</option>
                    <option value="bottom_right">二维码卡片：右下角</option>
                  </select>

                  <input type="file" accept="image/*" onChange={onUploadQr} />

                  <input
                    type="text"
                    placeholder="电话（可选，如 18720155555）"
                    value={form.qrPhoneNumber}
                    onChange={(e) => updateField("qrPhoneNumber", e.target.value)}
                  />

                  <label style={{ gridColumn: "1 / -1" }}>
                    二维码卡片尺寸：{Math.round((Number(form.qrScale) || 0.18) * 100)}%
                    <input
                      type="range"
                      min="0.08"
                      max="0.35"
                      step="0.01"
                      value={form.qrScale}
                      onChange={(e) => updateField("qrScale", Number(e.target.value))}
                    />
                  </label>
                </div>
                <p className="tip">{qrInfo ? `二维码已上传：${qrInfo.filename}` : "未上传二维码（可选）"}</p>
              </div>
            </>
          )}

          {error ? <div className="error-box">{error}</div> : null}
          {message ? <div className="tip">{message}</div> : null}

          <div className="postprocess-actions">
            <button type="button" className="generate-btn secondary" onClick={runPostprocess} disabled={processing}>
              {processing ? "处理中..." : `处理已选图片（${selectedPaths.length}）`}
            </button>
            <button type="button" className="generate-btn" onClick={loadImages} disabled={loadingList || processing}>
              {loadingList ? "刷新中..." : "刷新图片列表"}
            </button>
          </div>
        </section>

        <aside className="panel preview-panel postprocess-preview">
          <h2>已生成图片</h2>
          <div className="preview-actions">
            <button type="button" onClick={selectAll} disabled={!images.length}>
              全选
            </button>
            <button type="button" onClick={clearSelection} disabled={!selectedPaths.length}>
              清空选择
            </button>
          </div>

          <div className="set-grid postprocess-list">
            {images.map((item) => {
              const itemKey = item.record_id || item.path;
              return (
                <div key={itemKey} className="set-card">
                  <div className="set-card-head">
                    <strong title={item.filename}>{item.filename}</strong>
                    <div className="set-card-head-actions">
                      <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <input
                          type="checkbox"
                          checked={selectedSet.has(item.path)}
                          onChange={() => togglePath(item.path)}
                        />
                        选择
                      </label>
                      <button
                        type="button"
                        className="icon-btn-danger"
                        onClick={() => onDeleteImage(item)}
                        disabled={deletingKey === itemKey}
                        title="删除图片记录"
                        aria-label="删除图片记录"
                      >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                          <path d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 6h2v8h-2V9zm4 0h2v8h-2V9zM7 9h2v8H7V9zm1 12h8a2 2 0 0 0 2-2V9H6v10a2 2 0 0 0 2 2z" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  <div className="set-image-box">
                    <img
                      src={toAbsoluteUrl(item.path)}
                      alt={item.filename}
                      className="set-image zoomable-image"
                      onClick={() => openLightbox(toAbsoluteUrl(item.path), item.filename)}
                    />
                  </div>
                  <small className="tip">{item.path}</small>
                </div>
              );
            })}
          </div>
        </aside>
      </main>
      <ImageLightbox open={lightbox.open} src={lightbox.src} alt={lightbox.alt} onClose={closeLightbox} />
    </div>
  );
}

export default PostprocessPage;
