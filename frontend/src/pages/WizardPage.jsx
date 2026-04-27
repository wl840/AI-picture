import { useEffect, useMemo, useState } from "react";
import {
  fetchPosterOptions,
  generatePoster,
  postprocessImages,
  toAbsoluteUrl,
  uploadLogo,
  uploadQrImage,
} from "../api";
import ModelCard from "../components/ModelCard";
import LayoutCanvasPreview from "../components/LayoutCanvasPreview";

const DRAFT_KEY = "poster_wizard_draft_v1";
const DEFAULT_IMAGE_MODEL = "wan2.7-image-pro";
const DEFAULT_IMAGE_BASE_URL =
  import.meta.env.VITE_IMAGE_BASE_URL || "https://dashscope.aliyuncs.com/api/v1";

const GOAL_OPTIONS = [
  { key: "acquire", name: "拉新获客", template: "festival_promo" },
  { key: "convert", name: "促销转化", template: "product_showcase" },
  { key: "campaign", name: "活动宣传", template: "event_push" },
  { key: "brand", name: "品牌宣传", template: "brand_story" },
  { key: "recruit", name: "企业招聘", template: "recruitment" },
];

const FOCUS_OPTIONS = [
  { key: "scan_first", name: "扫码优先" },
  { key: "brand_first", name: "品牌优先" },
  { key: "balanced", name: "平衡" },
];

const STEP_ITEMS = [
  { key: 1, title: "品牌信息" },
  { key: 2, title: "目标与风格" },
  { key: 3, title: "布局预览" },
  { key: 4, title: "生成结果" },
];

const initialWizardForm = {
  apiKey: import.meta.env.VITE_DEFAULT_API_KEY || "",
  baseUrl: DEFAULT_IMAGE_BASE_URL,
  model: DEFAULT_IMAGE_MODEL,
  logoPosition: "top_right",
  qrPosition: "bottom_right",
  qrScale: 0.18,
  phone: "",
  wechat: "",
  companyName: "",
  mainTitle: "",
  subTitle: "",
  focusPriority: "balanced",
  goal: "acquire",
  style: "",
  ratioKey: "mobile",
  templateKey: "festival_promo",
  layoutPriority: "balanced",
};

const phoneRegex = /^[0-9+\-() ]{1,40}$/;
const wechatRegex = /^[a-zA-Z][-_a-zA-Z0-9]{5,39}$/;

function WizardPage() {
  const [form, setForm] = useState(initialWizardForm);
  const [step, setStep] = useState(1);
  const [maxReachedStep, setMaxReachedStep] = useState(1);
  const [options, setOptions] = useState(null);
  const [logoInfo, setLogoInfo] = useState(null);
  const [qrInfo, setQrInfo] = useState(null);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [generating, setGenerating] = useState(false);
  const [progressText, setProgressText] = useState("");
  const [result, setResult] = useState(null);

  const updateField = (name, value) => {
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const selectedGoal = useMemo(
    () => GOAL_OPTIONS.find((item) => item.key === form.goal) || GOAL_OPTIONS[0],
    [form.goal]
  );

  const styleOptions = options?.styles || [];

  useEffect(() => {
    const saved = localStorage.getItem(DRAFT_KEY);
    if (!saved) return;
    try {
      const draft = JSON.parse(saved);
      if (draft.form) {
        setForm((prev) => ({ ...prev, ...draft.form }));
      }
      if (draft.logoInfo) {
        setLogoInfo(draft.logoInfo);
      }
      if (draft.qrInfo) {
        setQrInfo(draft.qrInfo);
      }
      if (draft.step && Number.isInteger(draft.step) && draft.step >= 1 && draft.step <= 4) {
        setStep(draft.step);
        setMaxReachedStep(Math.max(1, draft.step));
      }
    } catch {
      // ignore invalid draft payload
    }
  }, []);

  useEffect(() => {
    async function loadOptions() {
      setLoadingOptions(true);
      setError("");
      try {
        const data = await fetchPosterOptions();
        const ratioKeys = Object.keys(data.aspect_ratios || {});
        const defaultRatio = ratioKeys.includes("mobile")
          ? "mobile"
          : ratioKeys.includes("square")
          ? "square"
          : ratioKeys[0] || "mobile";

        setOptions(data);
        setForm((prev) => ({
          ...prev,
          style: prev.style || data.styles?.[0]?.key || "",
          templateKey: prev.templateKey || data.templates?.[0]?.key || "festival_promo",
          ratioKey: ratioKeys.includes(prev.ratioKey) ? prev.ratioKey : defaultRatio,
        }));
      } catch (err) {
        setError(err.message || "加载配置失败");
      } finally {
        setLoadingOptions(false);
      }
    }

    loadOptions();
  }, []);

  useEffect(() => {
    const draft = {
      form,
      logoInfo,
      qrInfo,
      step,
    };
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  }, [form, logoInfo, qrInfo, step]);

  const saveDraft = () => {
    const draft = { form, logoInfo, qrInfo, step };
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    setMessage("草稿已保存");
    setError("");
  };

  const validateStep1 = () => {
    if (!form.companyName.trim()) return "请填写公司名称";
    if (!form.mainTitle.trim()) return "请填写主标题";
    if (form.mainTitle.trim().length > 20) return "主标题最多 20 个字符";
    if (form.subTitle.trim().length > 40) return "副标题最多 40 个字符";
    if (!form.phone.trim()) return "请填写联系电话";
    if (!phoneRegex.test(form.phone.trim())) {
      return "电话格式不正确，仅支持数字和 + - ( ) 空格";
    }
    if (form.wechat.trim() && !wechatRegex.test(form.wechat.trim())) {
      return "微信号格式不正确，建议字母开头，长度 6-40";
    }
    return "";
  };

  const validateStep2 = () => {
    if (!form.goal) return "请选择海报目标";
    if (!form.style) return "请选择风格";
    if (!form.apiKey.trim()) return "请先配置 API Key";
    return "";
  };

  const nextStep = () => {
    setMessage("");
    setError("");

    if (step === 1) {
      const err = validateStep1();
      if (err) {
        setError(err);
        return;
      }

      if (form.focusPriority === "scan_first" && !qrInfo?.qr_id) {
        setMessage("未上传二维码，已自动从“扫码优先”降级为“平衡”布局。");
        setForm((prev) => ({
          ...prev,
          focusPriority: "balanced",
          layoutPriority: prev.layoutPriority === "scan_first" ? "balanced" : prev.layoutPriority,
        }));
      }
    }

    if (step === 2) {
      const err = validateStep2();
      if (err) {
        setError(err);
        return;
      }
      if (selectedGoal?.template) {
        updateField("templateKey", selectedGoal.template);
      }
    }

    const next = Math.min(4, step + 1);
    setStep(next);
    setMaxReachedStep((prev) => Math.max(prev, next));
  };

  const prevStep = () => {
    setError("");
    setMessage("");
    setStep((prev) => Math.max(1, prev - 1));
  };

  const jumpStep = (target) => {
    if (target > maxReachedStep) return;
    setError("");
    setMessage("");
    setStep(target);
  };

  const onUploadLogo = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setError("");
    setMessage("");
    try {
      const uploaded = await uploadLogo(file);
      setLogoInfo({
        ...uploaded,
        url: toAbsoluteUrl(uploaded.url),
      });
      setMessage(`Logo 上传成功：${uploaded.filename}`);
    } catch (err) {
      setError(err.message || "Logo 上传失败");
    }
  };

  const onUploadQr = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setError("");
    setMessage("");
    try {
      const uploaded = await uploadQrImage(file);
      setQrInfo({
        ...uploaded,
        url: toAbsoluteUrl(uploaded.url),
      });
      setMessage(`二维码上传成功：${uploaded.filename}`);
    } catch (err) {
      setError(err.message || "二维码上传失败");
    }
  };

  const buildHighlights = () => {
    const focusMap = {
      scan_first: "重点引导扫码转化",
      brand_first: "突出品牌露出与可信度",
      balanced: "品牌信息与转化信息平衡",
    };

    return [selectedGoal?.name || "品牌宣传", focusMap[form.layoutPriority] || focusMap.balanced];
  };

  const buildDescription = () => {
    const lines = [
      `公司名称：${form.companyName.trim()}`,
      `主标题：${form.mainTitle.trim()}`,
      form.subTitle.trim() ? `副标题：${form.subTitle.trim()}` : "",
      form.wechat.trim() ? `微信号：${form.wechat.trim()}` : "",
      `联系电话：${form.phone.trim()}`,
      `布局重点：${FOCUS_OPTIONS.find((item) => item.key === form.layoutPriority)?.name || "平衡"}`,
    ].filter(Boolean);

    return lines.join("；");
  };

  const runGenerate = async () => {
    setError("");
    setMessage("");

    const step1Error = validateStep1();
    if (step1Error) {
      setError(step1Error);
      setStep(1);
      return;
    }

    const step2Error = validateStep2();
    if (step2Error) {
      setError(step2Error);
      setStep(2);
      return;
    }

    setGenerating(true);
    setProgressText("正在生成基础海报（1/2）...");

    try {
      const generated = await generatePoster({
        api_key: form.apiKey.trim(),
        base_url: form.baseUrl.trim(),
        model: form.model,
        template_key: selectedGoal?.template || form.templateKey,
        style: form.style,
        ratio_key: form.ratioKey,
        product_name: form.mainTitle.trim(),
        highlights: buildHighlights(),
        description: buildDescription(),
        logo_id: null,
        logo_mode: "fixed",
        logo_position: form.logoPosition,
      });

      let finalSavedPath = generated.saved_path || "";
      const needOverlay = Boolean(logoInfo?.logo_id || qrInfo?.qr_id);

      if (needOverlay && finalSavedPath) {
        setProgressText("正在融合品牌资产（2/2）...");
        const postResult = await postprocessImages({
          image_paths: [finalSavedPath],
          process_mode: "local",
          logo_id: logoInfo?.logo_id || null,
          logo_position: form.logoPosition,
          watermark_text: "",
          watermark_position: "bottom_right",
          text_content: "",
          text_position: "top_left",
          qr_enabled: Boolean(qrInfo?.qr_id),
          qr_image_id: qrInfo?.qr_id || null,
          qr_position: form.qrPosition,
          qr_scale: Number(form.qrScale) || 0.18,
          phone_number: form.phone.trim(),
          api_key: form.apiKey.trim(),
          model: form.model,
          base_url: form.baseUrl.trim(),
          ai_prompt: "",
        });

        const first = (postResult?.items || [])[0];
        if (first?.saved_path) {
          finalSavedPath = first.saved_path;
        }
      }

      setResult({
        prompt: generated.prompt,
        basePath: generated.saved_path || "",
        finalPath: finalSavedPath || generated.saved_path || "",
        imageUrl: toAbsoluteUrl(finalSavedPath || generated.saved_path || generated.image_url || ""),
      });
      setMessage("生成完成，可以下载或重新生成。");
      setProgressText("生成完成");
      setStep(4);
      setMaxReachedStep(4);
    } catch (err) {
      setError(err.message || "生成失败");
      setProgressText("生成失败");
      setStep(4);
      setMaxReachedStep(4);
    } finally {
      setGenerating(false);
    }
  };

  const downloadResult = () => {
    if (!result?.imageUrl) return;
    const link = document.createElement("a");
    link.href = result.imageUrl;
    link.download = `poster_${Date.now()}.png`;
    link.click();
  };

  const renderStep1 = () => (
    <div className="wizard-step-panel">
      <h2>第一步：品牌信息</h2>
      <div className="form-group">
        <div className="upload-field">
          <label>上传 Logo（PNG/JPG）</label>
          <input type="file" accept="image/*" onChange={onUploadLogo} />
          <small>{logoInfo ? `已上传：${logoInfo.filename}` : "未上传"}</small>
        </div>

        <div className="upload-field">
          <label>上传二维码（PNG/JPG）</label>
          <input type="file" accept="image/*" onChange={onUploadQr} />
          <small>{qrInfo ? `已上传：${qrInfo.filename}` : "未上传"}</small>
        </div>

        <input
          type="text"
          placeholder="联系电话（必填）"
          value={form.phone}
          onChange={(e) => updateField("phone", e.target.value)}
        />
        <input
          type="text"
          placeholder="微信号（可选）"
          value={form.wechat}
          onChange={(e) => updateField("wechat", e.target.value)}
        />

        <input
          type="text"
          placeholder="公司名称（必填）"
          value={form.companyName}
          onChange={(e) => updateField("companyName", e.target.value)}
        />
        <input
          type="text"
          placeholder="主标题（必填，最多20字）"
          value={form.mainTitle}
          onChange={(e) => updateField("mainTitle", e.target.value)}
        />

        <textarea
          placeholder="副标题（可选，最多40字）"
          value={form.subTitle}
          onChange={(e) => updateField("subTitle", e.target.value)}
        />
      </div>

      <div className="section">
        <h2>主要突出</h2>
        <div className="chips">
          {FOCUS_OPTIONS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`chip ${form.focusPriority === item.key ? "active" : ""}`}
              onClick={() => {
                updateField("focusPriority", item.key);
                updateField("layoutPriority", item.key);
              }}
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );

  const renderStep2 = () => (
    <div className="wizard-step-panel">
      <h2>第二步：目标与风格</h2>

      <div className="section">
        <h2>海报目标</h2>
        <div className="chips">
          {GOAL_OPTIONS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`chip ${form.goal === item.key ? "active" : ""}`}
              onClick={() => updateField("goal", item.key)}
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>

      <div className="section">
        <h2>风格选择</h2>
        <div className="chips">
          {styleOptions.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`chip ${form.style === item.key ? "active" : ""}`}
              onClick={() => updateField("style", item.key)}
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>

      <div className="section">
        <h2>模型选择</h2>
        <ModelCard
          title="阿里云 wan2.7-image-pro"
          description="当前按你的默认配置，仅启用一个模型。后续可直接扩展多模型卡片。"
          selected={form.model === DEFAULT_IMAGE_MODEL}
          onSelect={() => updateField("model", DEFAULT_IMAGE_MODEL)}
        />
        <div className="model-demo-placeholder">模型效果对比区（当前仅 1 个模型，后续可扩展）</div>
      </div>

      <div className="section form-group">
        <select value={form.ratioKey} onChange={(e) => updateField("ratioKey", e.target.value)}>
          <option value="mobile">9:16 竖版</option>
          <option value="square">1:1 方图</option>
          <option value="landscape">16:9 横版</option>
        </select>
        <input
          type="password"
          placeholder="API Key"
          value={form.apiKey}
          onChange={(e) => updateField("apiKey", e.target.value)}
        />
      </div>
    </div>
  );

  const renderStep3 = () => (
    <div className="wizard-step-panel">
      <h2>第三步：布局预览</h2>

      <div className="section">
        <h2>布局策略</h2>
        <div className="chips">
          {FOCUS_OPTIONS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`chip ${form.layoutPriority === item.key ? "active" : ""}`}
              onClick={() => updateField("layoutPriority", item.key)}
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>

      <div className="form-group">
        <select value={form.logoPosition} onChange={(e) => updateField("logoPosition", e.target.value)}>
          <option value="top_left">Logo：左上角</option>
          <option value="top_right">Logo：右上角</option>
          <option value="bottom_left">Logo：左下角</option>
          <option value="bottom_right">Logo：右下角</option>
        </select>

        <select value={form.qrPosition} onChange={(e) => updateField("qrPosition", e.target.value)}>
          <option value="bottom_left">二维码：左下角</option>
          <option value="bottom_right">二维码：右下角</option>
        </select>
      </div>

      <label className="range-label">
        二维码大小：{Math.round((Number(form.qrScale) || 0.18) * 100)}%
        <input
          type="range"
          min="0.1"
          max="0.35"
          step="0.01"
          value={form.qrScale}
          onChange={(e) => updateField("qrScale", Number(e.target.value))}
        />
      </label>

      <LayoutCanvasPreview form={form} logoInfo={logoInfo} qrInfo={qrInfo} />
    </div>
  );

  const renderStep4 = () => (
    <div className="wizard-step-panel">
      <h2>第四步：生成结果</h2>
      <p className="tip">点击下方“开始生成”后，会按你前面配置自动完成生成与品牌融合。</p>

      <div className="wizard-result-box">
        {result?.imageUrl ? (
          <img src={result.imageUrl} alt="海报生成结果" className="poster-image" />
        ) : (
          <div className="empty-box" style={{ minHeight: 380 }}>
            <p>结果图将在这里展示</p>
            <small>请先点击开始生成</small>
          </div>
        )}
      </div>

      <div className="preview-actions">
        <button type="button" onClick={downloadResult} disabled={!result?.imageUrl}>
          下载结果
        </button>
        <button type="button" onClick={runGenerate} disabled={generating}>
          {generating ? "生成中..." : "重新生成"}
        </button>
      </div>

      <details className="prompt-box">
        <summary>查看本次生成提示词</summary>
        <pre>{result?.prompt || "生成后展示"}</pre>
      </details>
    </div>
  );

  const stepContent = useMemo(() => {
    if (step === 1) return renderStep1();
    if (step === 2) return renderStep2();
    if (step === 3) return renderStep3();
    return renderStep4();
  }, [step, form, logoInfo, qrInfo, result, generating, options]);

  return (
    <div className="page-wrap">
      <main className="board wizard-board">
        <section className="panel form-panel wizard-panel">
          <h1>海报向导</h1>

          <div className="wizard-steps">
            {STEP_ITEMS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`wizard-step ${step === item.key ? "active" : ""} ${
                  item.key <= maxReachedStep ? "clickable" : "disabled"
                }`}
                onClick={() => jumpStep(item.key)}
                disabled={item.key > maxReachedStep}
              >
                <span>{item.key}</span>
                <strong>{item.title}</strong>
              </button>
            ))}
          </div>

          {loadingOptions ? <div className="tip">配置加载中...</div> : stepContent}

          {error ? <div className="error-box">{error}</div> : null}
          {message ? <div className="tip">{message}</div> : null}
          {progressText ? <div className="tip">{progressText}</div> : null}

          <div className="wizard-actions">
            <button type="button" className="generate-btn secondary" onClick={saveDraft}>
              保存草稿
            </button>

            <div className="wizard-actions-right">
              <button type="button" className="generate-btn" onClick={prevStep} disabled={step === 1 || generating}>
                上一步
              </button>

              {step < 4 ? (
                <button type="button" className="generate-btn" onClick={nextStep} disabled={generating}>
                  下一步
                </button>
              ) : (
                <button type="button" className="generate-btn" onClick={runGenerate} disabled={generating}>
                  {generating ? "生成中..." : "开始生成"}
                </button>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default WizardPage;
