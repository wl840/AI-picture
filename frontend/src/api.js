const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export async function fetchPosterOptions() {
  const res = await fetch(`${API_BASE}/api/poster/options`);
  if (!res.ok) {
    throw new Error(`加载配置失败: ${res.status}`);
  }
  return res.json();
}

export async function uploadLogo(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/poster/upload-logo`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Logo 上传失败: ${text}`);
  }
  return res.json();
}

export async function uploadProductImage(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/product/upload-image`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`产品图上传失败: ${text}`);
  }
  return res.json();
}

export async function generatePoster(payload) {
  const res = await fetch(`${API_BASE}/api/poster/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`生成失败: ${text}`);
  }
  return res.json();
}

export async function generateProductSet(payload) {
  const res = await fetch(`${API_BASE}/api/product/generate-set`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`五图生成失败: ${text}`);
  }
  return res.json();
}

export async function postprocessImages(payload) {
  const res = await fetch(`${API_BASE}/api/poster/postprocess`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`后处理失败: ${text}`);
  }
  return res.json();
}

export async function fetchGeneratedImages() {
  const res = await fetch(`${API_BASE}/api/poster/generated-images`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`加载已生成图片失败: ${text}`);
  }
  return res.json();
}

export async function fetchImageRecords() {
  const res = await fetch(`${API_BASE}/api/poster/image-records`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`加载图片记录失败: ${text}`);
  }
  return res.json();
}

export async function deleteGeneratedImage(path) {
  const res = await fetch(`${API_BASE}/api/poster/generated-images/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`删除失败: ${text}`);
  }
  return res.json();
}

export async function deleteImageRecord(recordId) {
  const res = await fetch(`${API_BASE}/api/poster/image-records/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ record_id: recordId }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`删除失败: ${text}`);
  }
  return res.json();
}

export async function generateComic(payload) {
  const res = await fetch(`${API_BASE}/api/poster/generate-comic`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`漫画生成失败: ${text}`);
  }
  return res.json();
}

export async function createComicTask(payload) {
  const res = await fetch(`${API_BASE}/api/poster/generate-comic/task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`漫画任务创建失败: ${text}`);
  }
  return res.json();
}

export async function fetchComicTaskStatus(taskId) {
  const res = await fetch(`${API_BASE}/api/poster/generate-comic/task/${taskId}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`漫画任务查询失败: ${text}`);
  }
  return res.json();
}

export function toAbsoluteUrl(url) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:")) {
    return url;
  }
  return `${API_BASE}${url}`;
}
