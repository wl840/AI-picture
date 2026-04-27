const LAYOUT_MAP = {
  balanced: {
    qrRight: "6%",
    titleWidth: "54%",
    titleLeft: "6%",
  },
  brand_first: {
    qrRight: "10%",
    titleWidth: "64%",
    titleLeft: "6%",
  },
  scan_first: {
    qrRight: "4%",
    titleWidth: "46%",
    titleLeft: "6%",
  },
};

function getCornerStyle(position, size = 64) {
  const base = {
    width: `${size}px`,
    height: `${size}px`,
  };

  if (position === "top_left") return { ...base, top: "8%", left: "6%" };
  if (position === "bottom_left") return { ...base, bottom: "11%", left: "6%" };
  if (position === "bottom_right") return { ...base, bottom: "11%", right: "6%" };
  return { ...base, top: "8%", right: "6%" };
}

function getQrStyle(position, size = 74) {
  const base = {
    width: `${size}px`,
    height: `${size}px`,
    bottom: "10%",
  };

  if (position === "bottom_left") return { ...base, left: "6%" };
  return { ...base, right: "6%" };
}

function LayoutCanvasPreview({ form, logoInfo, qrInfo }) {
  const layout = LAYOUT_MAP[form.layoutPriority] || LAYOUT_MAP.balanced;

  return (
    <div className="layout-canvas">
      <div className="layout-gradient" />

      <div className="layout-block logo" style={getCornerStyle(form.logoPosition)}>
        {logoInfo ? <img src={logoInfo.url} alt="logo" /> : <span>LOGO</span>}
      </div>

      <div className="layout-title" style={{ width: layout.titleWidth, left: layout.titleLeft }}>
        <h3>{form.mainTitle || "主标题"}</h3>
        <p>{form.subTitle || "副标题"}</p>
      </div>

      <div className="layout-story">
        <div className="story-grid">
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>

      <div className="layout-cta">{form.goal || "活动目标"}</div>

      <div
        className="layout-block qr"
        style={getQrStyle(form.qrPosition, Math.round((form.qrScale || 0.18) * 360))}
      >
        {qrInfo ? <img src={qrInfo.url} alt="二维码" /> : <span>QR</span>}
      </div>

      <div
        className={`layout-phone ${form.qrPosition === "bottom_left" ? "left" : "right"}`}
        style={{ right: form.qrPosition === "bottom_right" ? layout.qrRight : "auto" }}
      >
        热线：{form.phone || "400-888-6666"}
      </div>
    </div>
  );
}

export default LayoutCanvasPreview;
