import { useEffect, useMemo, useState } from "react";
import { fetchPosterOptions, generatePoster, toAbsoluteUrl, uploadLogo } from "./api";

const DEFAULT_IMAGE_MODEL = "qwen-image-2.0-pro";
const DEFAULT_IMAGE_BASE_URL =
  import.meta.env.VITE_IMAGE_BASE_URL || "https://dashscope.aliyuncs.com/compatible-mode/v1";

const initialForm = {
  apiKey: import.meta.env.VITE_DEFAULT_API_KEY || "",
  templateKey: "",
  productName: "",
  highlightsText: "",
  description: "",
  style: "",
  ratioKey: "square",
};

function App() {
  const [options, setOptions] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [logoInfo, setLogoInfo] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
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

  const updateField = (name, value) => {
    setForm((prev) => ({ ...prev, [name]: value }));
  };

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
      const highlights = form.highlightsText
        .split(/[，,;；]/)
        .map((item) => item.trim())
        .filter(Boolean);

      const payload = {
        api_key: form.apiKey.trim(),
        base_url: DEFAULT_IMAGE_BASE_URL,
        model: DEFAULT_IMAGE_MODEL,
        template_key: form.templateKey,
        style: form.style,
        ratio_key: form.ratioKey,
        product_name: form.productName.trim(),
        highlights,
        description: form.description.trim(),
        logo_id: logoInfo?.logo_id || null,
      };

      const generated = await generatePoster(payload);
      setResult(generated);
    } catch (err) {
      setError(err.message || "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const onDownload = () => {
    if (!resultImage) return;
    const link = document.createElement("a");
    link.href = resultImage;
    link.download = `poster_${Date.now()}.png`;
    link.click();
  };

  return (
    <div className="page-wrap">
      <div className="glow glow-left" />
      <div className="glow glow-right" />

      <main className="board">
        <section className="panel form-panel">
          <h1>海报生成配置</h1>

          <div className="section">
            <h2>选择模板</h2>
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
                placeholder="产品/活动名称"
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
                placeholder="详细描述（可选）"
                value={form.description}
                onChange={(e) => updateField("description", e.target.value)}
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
            <h2>品牌 Logo（可选）</h2>
            <div className="upload-row">
              <input type="file" accept="image/*" onChange={onUploadLogo} />
              <div className="upload-info">
                {logoInfo ? `已上传：${logoInfo.filename}` : "未上传"}
              </div>
            </div>
          </div>

          {error ? <div className="error-box">{error}</div> : null}

          <button type="button" className="generate-btn" onClick={onGenerate} disabled={loading}>
            {loading ? "生成中..." : "AI 生成海报"}
          </button>
        </section>

        <aside className="panel preview-panel">
          <h2>预览区域</h2>
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
            <button type="button" onClick={onDownload} disabled={!resultImage}>
              下载
            </button>
            <button type="button" disabled>
              定时发布（预留）
            </button>
          </div>

          <details className="prompt-box">
            <summary>查看提示词</summary>
            <pre>{result?.prompt || "生成后展示 Prompt"}</pre>
          </details>

          <div className="tip">
            当前模板：{templateMap.get(form.templateKey)?.name || "-"} | 模型：{DEFAULT_IMAGE_MODEL}
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;
