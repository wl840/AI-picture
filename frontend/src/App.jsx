import { useEffect, useMemo, useState } from "react";
import {
  fetchPosterOptions,
  generatePoster,
  generateProductSet,
  toAbsoluteUrl,
  uploadLogo,
  uploadProductImage,
} from "./api";

const DEFAULT_IMAGE_MODEL = "qwen-image-2.0-pro";
const DEFAULT_IMAGE_BASE_URL =
  import.meta.env.VITE_IMAGE_BASE_URL || "https://dashscope.aliyuncs.com/compatible-mode/v1";

const initialForm = {
  apiKey: import.meta.env.VITE_DEFAULT_API_KEY || "",
  templateKey: "",
  productName: "",
  highlightsText: "",
  description: "",
  sceneDescription: "",
  specsText: "",
  style: "",
  ratioKey: "square",
  logoMode: "fixed",
  logoPosition: "top_right",
};

function App() {
  const [options, setOptions] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [logoInfo, setLogoInfo] = useState(null);
  const [productImageInfo, setProductImageInfo] = useState(null);
  const [result, setResult] = useState(null);
  const [productSetResult, setProductSetResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [productSetLoading, setProductSetLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadOptions() {
      try {
        const data = await fetchPosterOptions();
        setOptions(data);
        setForm((prev) => ({
          ...prev,
          templateKey: data.templates?.[0]?.key || "festival_promo",
          style: data.styles?.[0] || "简约商务",
          ratioKey: Object.keys(data.aspect_ratios || {})[0] || "square",
        }));
      } catch (err) {
        setError(err.message || "配置加载失败");
      }
    }
    loadOptions();
  }, []);

  const templateMap = useMemo(() => {
    const map = new Map();
    (options?.templates || []).forEach((item) => map.set(item.key, item));
    return map;
  }, [options]);

  const ratioEntries = useMemo(
    () => Object.entries(options?.aspect_ratios || {}),
    [options]
  );

  const resultImage = useMemo(() => {
    if (!result) return "";
    if (result.image_url) return toAbsoluteUrl(result.image_url);
    if (result.saved_path) return toAbsoluteUrl(result.saved_path);
    if (result.image_base64) return `data:image/png;base64,${result.image_base64}`;
    return "";
  }, [result]);

  const productSetItems = useMemo(() => {
    return (productSetResult?.items || []).map((item) => {
      let image = "";
      if (item.image_url) image = toAbsoluteUrl(item.image_url);
      else if (item.saved_path) image = toAbsoluteUrl(item.saved_path);
      else if (item.image_base64) image = `data:image/png;base64,${item.image_base64}`;

      return {
        ...item,
        image,
      };
    });
  }, [productSetResult]);

  const updateField = (name, value) => {
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const splitTextToList = (text) =>
    text
      .split(/[，,;；\n]/)
      .map((item) => item.trim())
      .filter(Boolean);

  const onUploadLogo = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setError("");
    try {
      const uploaded = await uploadLogo(file);
      setLogoInfo(uploaded);
    } catch (err) {
      setError(err.message || "Logo 上传失败");
    }
  };

  const onUploadProductImage = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setError("");
    try {
      const uploaded = await uploadProductImage(file);
      setProductImageInfo(uploaded);
    } catch (err) {
      setError(err.message || "产品图上传失败");
    }
  };

  const onGenerate = async () => {
    if (!form.apiKey.trim()) {
      setError("请在 frontend/.env 中配置 VITE_DEFAULT_API_KEY");
      return;
    }
    if (!form.productName.trim()) {
      setError("请填写产品/活动名称");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const payload = {
        api_key: form.apiKey.trim(),
        base_url: DEFAULT_IMAGE_BASE_URL,
        model: DEFAULT_IMAGE_MODEL,
        template_key: form.templateKey,
        style: form.style,
        ratio_key: form.ratioKey,
        product_name: form.productName.trim(),
        highlights: splitTextToList(form.highlightsText),
        description: form.description.trim(),
        logo_id: logoInfo?.logo_id || null,
        logo_mode: form.logoMode,
        logo_position: form.logoMode === "fixed" ? form.logoPosition : null,
      };

      const generated = await generatePoster(payload);
      setResult(generated);
    } catch (err) {
      setError(err.message || "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const onGenerateProductSet = async () => {
    if (!form.apiKey.trim()) {
      setError("请在 frontend/.env 中配置 VITE_DEFAULT_API_KEY");
      return;
    }
    if (!form.productName.trim()) {
      setError("请填写产品名称");
      return;
    }
    if (!productImageInfo?.product_image_id) {
      setError("请先上传产品参考图");
      return;
    }

    setProductSetLoading(true);
    setError("");

    try {
      const payload = {
        api_key: form.apiKey.trim(),
        base_url: DEFAULT_IMAGE_BASE_URL,
        model: DEFAULT_IMAGE_MODEL,
        product_image_id: productImageInfo.product_image_id,
        product_name: form.productName.trim(),
        style: form.style,
        ratio_key: form.ratioKey,
        highlights: splitTextToList(form.highlightsText),
        description: form.description.trim(),
        scene_description: form.sceneDescription.trim(),
        specs: splitTextToList(form.specsText),
      };

      const generated = await generateProductSet(payload);
      setProductSetResult(generated);
    } catch (err) {
      setError(err.message || "五图生成失败");
    } finally {
      setProductSetLoading(false);
    }
  };

  const downloadImage = (url, prefix = "poster") => {
    if (!url) return;
    const link = document.createElement("a");
    link.href = url;
    link.download = `${prefix}_${Date.now()}.png`;
    link.click();
  };

  return (
    <div className="page-wrap">
      <div className="glow glow-left" />
      <div className="glow glow-right" />

      <main className="board">
        <section className="panel form-panel">
          <h1>海报与商品五图生成</h1>

          <div className="section">
            <h2>选择模板（海报模式）</h2>
            <div className="template-grid">
              {(options?.templates || []).map((template) => (
                <button
                  key={template.key}
                  type="button"
                  className={`template-card ${
                    form.templateKey === template.key ? "active" : ""
                  }`}
                  onClick={() => updateField("templateKey", template.key)}
                >
                  <span className="dot" />
                  <strong>{template.name}</strong>
                  <small>{template.variants} 种变体</small>
                </button>
              ))}
            </div>
          </div>

          <div className="section">
            <h2>产品信息</h2>
            <div className="form-group">
              <input
                type="text"
                placeholder="产品名称"
                value={form.productName}
                onChange={(e) => updateField("productName", e.target.value)}
              />
              <input
                type="text"
                placeholder="核心卖点（用逗号分隔）"
                value={form.highlightsText}
                onChange={(e) => updateField("highlightsText", e.target.value)}
              />
              <textarea
                placeholder="产品描述（可选）"
                value={form.description}
                onChange={(e) => updateField("description", e.target.value)}
              />
              <input
                type="text"
                placeholder="应用场景补充（可选）"
                value={form.sceneDescription}
                onChange={(e) => updateField("sceneDescription", e.target.value)}
              />
              <input
                type="text"
                placeholder="尺寸规格（如：长20cm,宽10cm,高5cm）"
                value={form.specsText}
                onChange={(e) => updateField("specsText", e.target.value)}
              />
            </div>
          </div>

          <div className="section">
            <h2>风格选择</h2>
            <div className="chips">
              {(options?.styles || []).map((style) => (
                <button
                  key={style}
                  type="button"
                  className={`chip ${form.style === style ? "active" : ""}`}
                  onClick={() => updateField("style", style)}
                >
                  {style}
                </button>
              ))}
            </div>
          </div>

          <div className="section">
            <h2>尺寸比例</h2>
            <div className="ratio-grid">
              {ratioEntries.map(([key, value]) => (
                <button
                  key={key}
                  type="button"
                  className={`ratio-card ${form.ratioKey === key ? "active" : ""}`}
                  onClick={() => updateField("ratioKey", key)}
                >
                  <strong>{value.label}</strong>
                  <small>{value.size}</small>
                </button>
              ))}
            </div>
          </div>

          <div className="section">
            <h2>品牌 Logo（海报模式可选）</h2>
            <div className="form-group">
              <select
                value={form.logoMode}
                onChange={(e) => updateField("logoMode", e.target.value)}
              >
                <option value="fixed">固定位置模式（推荐）</option>
                <option value="ai">AI 自由融合模式</option>
              </select>

              {form.logoMode === "fixed" ? (
                <select
                  value={form.logoPosition}
                  onChange={(e) => updateField("logoPosition", e.target.value)}
                >
                  <option value="top_left">左上角</option>
                  <option value="top_right">右上角</option>
                  <option value="bottom_left">左下角</option>
                  <option value="bottom_right">右下角</option>
                </select>
              ) : (
                <input type="text" value="AI 自动决定位置与融合风格" readOnly />
              )}
            </div>

            <div className="upload-row">
              <input type="file" accept="image/*" onChange={onUploadLogo} />
              <div className="upload-info">
                {logoInfo ? `已上传：${logoInfo.filename}` : "未上传"}
              </div>
            </div>
          </div>

          <div className="section">
            <h2>产品参考图（五图模式必传）</h2>
            <div className="upload-row">
              <input type="file" accept="image/*" onChange={onUploadProductImage} />
              <div className="upload-info">
                {productImageInfo ? `已上传：${productImageInfo.filename}` : "未上传"}
              </div>
            </div>
          </div>

          {error ? <div className="error-box">{error}</div> : null}

          <div className="action-grid">
            <button type="button" className="generate-btn" onClick={onGenerate} disabled={loading}>
              {loading ? "海报生成中..." : "AI 生成海报"}
            </button>
            <button
              type="button"
              className="generate-btn secondary"
              onClick={onGenerateProductSet}
              disabled={productSetLoading}
            >
              {productSetLoading ? "五图生成中..." : "AI 生成商品五图"}
            </button>
          </div>
        </section>

        <aside className="panel preview-panel">
          <h2>海报预览</h2>
          <div className="preview-box">
            {resultImage ? (
              <img src={resultImage} alt="生成海报" className="poster-image" />
            ) : (
              <div className="empty-box">
                <p>生成后预览</p>
                <small>选择模板并填写信息后点击生成</small>
              </div>
            )}
          </div>

          <div className="preview-actions">
            <button type="button" onClick={() => downloadImage(resultImage, "poster")} disabled={!resultImage}>
              下载海报
            </button>
            <button type="button" disabled>
              定时发布（预留）
            </button>
          </div>

          <details className="prompt-box">
            <summary>查看海报提示词</summary>
            <pre>{result?.prompt || "生成后展示 Prompt"}</pre>
          </details>

          <div className="tip">
            当前模板：{templateMap.get(form.templateKey)?.name || "-"} | 模型：{DEFAULT_IMAGE_MODEL}
          </div>

          <h2 className="set-title">五图结果（{productSetResult?.success_count || 0}/5）</h2>
          {productSetItems.length ? (
            <div className="set-grid">
              {productSetItems.map((item) => (
                <div key={item.key} className="set-card">
                  <div className="set-card-head">
                    <strong>{item.name}</strong>
                    <span className={`set-status ${item.error ? "error" : "ok"}`}>
                      {item.error ? "失败" : "完成"}
                    </span>
                  </div>

                  <div className="set-image-box">
                    {item.image ? (
                      <img src={item.image} alt={item.name} className="set-image" />
                    ) : (
                      <div className="set-empty">{item.error ? "生成失败" : "等待生成"}</div>
                    )}
                  </div>

                  <div className="set-actions">
                    <button
                      type="button"
                      onClick={() => downloadImage(item.image, item.key)}
                      disabled={!item.image}
                    >
                      下载
                    </button>
                  </div>

                  <details className="prompt-box mini">
                    <summary>查看提示词</summary>
                    <pre>{item.prompt}</pre>
                  </details>

                  {item.error ? <div className="error-inline">{item.error}</div> : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="set-empty-state">上传产品参考图后点击“AI 生成商品五图”</div>
          )}
        </aside>
      </main>
    </div>
  );
}

export default App;
