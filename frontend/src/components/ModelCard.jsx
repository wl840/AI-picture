function ModelCard({ title, description, selected, onSelect }) {
  return (
    <button
      type="button"
      className={`model-card ${selected ? "active" : ""}`}
      onClick={onSelect}
    >
      <div className="model-card-head">
        <strong>{title}</strong>
        <span className="model-chip">当前可用</span>
      </div>
      <p>{description}</p>
      <small>后续可扩展豆包 / Qwen / Gemini 多模型对比</small>
    </button>
  );
}

export default ModelCard;
