import { useEffect, useMemo, useState } from "react";
import {
  fetchGeneratedImages,
  postprocessImages,
  toAbsoluteUrl,
  uploadLogo,
} from "../api";

const DEFAULT_IMAGE_BASE_URL =
  import.meta.env.VITE_IMAGE_BASE_URL || "https://dashscope.aliyuncs.com/compatible-mode/v1";

const initialForm = {
  processMode: "local",
  useLogo: true,
  logoPosition: "bottom_right",
  watermarkText: "",
  watermarkPosition: "bottom_right",
  textContent: "",
  textPosition: "top_left",
  apiKey: import.meta.env.VITE_DEFAULT_API_KEY || "",
  model: "qwen-image-2.0-pro",
  baseUrl: DEFAULT_IMAGE_BASE_URL,
  aiPrompt:
    "在保持原图主体构图与风格的前提下，融合参考logo到画面中，保证清晰、自然，不遮挡主体，不要水印和乱码。",
  aiRatioKey: "square",
};

function PostprocessPage() {
  const [form, setForm] = useState(initialForm);
  const [images, setImages] = useState([]);
  const [selectedPaths, setSelectedPaths] = useState([]);
  const [logoInfo, setLogoInfo] = useState(null);
  const [loadingList, setLoadingList] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const selectedSet = useMemo(() => new Set(selectedPaths), [selectedPaths]);

  const updateField = (name, value) => {
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const loadImages = async () => {
    setLoadingList(true);
    setError("");
    try {
      const list = await fetchGeneratedImages();
      setImages(list || []);
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

  const runPostprocess = async () => {
    if (!selectedPaths.length) {
      setError("请先选择要处理的图片。");
      return;
    }

    const hasLogo = form.useLogo && !!logoInfo?.logo_id;
    if (form.processMode === "local" && !hasLogo && !form.watermarkText.trim() && !form.textContent.trim()) {
      setError("本地模式下请至少启用一项：Logo、水印或文字。");
      return;
    }
    if (form.processMode === "ai" && !form.apiKey.trim()) {
      setError("AI 模式需要 API Key。");
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
        api_key: form.apiKey.trim(),
        model: form.model.trim(),
        base_url: form.baseUrl.trim(),
        ai_prompt: form.aiPrompt.trim(),
        ai_ratio_key: form.aiRatioKey,
      });
      const success = result?.success_count || 0;
      const failed = (result?.items || []).filter((item) => item.error).length;
      setMessage(`处理完成：成功 ${success} 张，失败 ${failed} 张。`);
      await loadImages();
      const newPaths = (result?.items || []).map((item) => item.saved_path).filter(Boolean);
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
            <div className="section">
              <h2>本地叠加参数</h2>
              <div className="form-group">
                <input
                  type="text"
                  placeholder="水印文字（可选）"
                  value={form.watermarkText}
                  onChange={(e) => updateField("watermarkText", e.target.value)}
                />
                <select
                  value={form.watermarkPosition}
                  onChange={(e) => updateField("watermarkPosition", e.target.value)}
                >
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
          ) : (
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
                  placeholder="模型名（如 qwen-image-2.0-pro）"
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
                <textarea
                  placeholder="AI 编辑提示词"
                  value={form.aiPrompt}
                  onChange={(e) => updateField("aiPrompt", e.target.value)}
                />
              </div>
              <p className="tip">AI 模式会把“原图 + logo图（如果上传）”一起作为参考图发给模型。</p>
            </div>
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
            {images.map((item) => (
              <div key={item.path} className="set-card">
                <div className="set-card-head">
                  <strong title={item.filename}>{item.filename}</strong>
                  <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <input
                      type="checkbox"
                      checked={selectedSet.has(item.path)}
                      onChange={() => togglePath(item.path)}
                    />
                    选择
                  </label>
                </div>
                <div className="set-image-box">
                  <img src={toAbsoluteUrl(item.path)} alt={item.filename} className="set-image" />
                </div>
                <small className="tip">{item.path}</small>
              </div>
            ))}
          </div>
        </aside>
      </main>
    </div>
  );
}

export default PostprocessPage;
