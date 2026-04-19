import { useEffect, useMemo, useState } from "react";

import GeneratorPage from "./pages/GeneratorPage";
import PostprocessPage from "./pages/PostprocessPage";

function getCurrentRoute() {
  const hash = window.location.hash || "#/generate";
  if (hash.startsWith("#/postprocess")) return "postprocess";
  return "generate";
}

function App() {
  const [route, setRoute] = useState(getCurrentRoute());

  useEffect(() => {
    const onHashChange = () => setRoute(getCurrentRoute());
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) window.location.hash = "#/generate";
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const title = useMemo(
    () => (route === "postprocess" ? "后处理页面（#/postprocess）" : "生成页面（#/generate）"),
    [route]
  );

  return (
    <div>
      <header className="top-nav">
        <div className="top-nav-inner">
          <strong>AI Poster Studio</strong>
          <nav className="top-nav-links">
            <a href="#/generate" className={route === "generate" ? "active" : ""}>
              生成页
            </a>
            <a href="#/postprocess" className={route === "postprocess" ? "active" : ""}>
              后处理页
            </a>
          </nav>
          <small>{title}</small>
        </div>
      </header>

      <div style={{ display: route === "generate" ? "block" : "none" }}>
        <GeneratorPage />
      </div>
      <div style={{ display: route === "postprocess" ? "block" : "none" }}>
        <PostprocessPage />
      </div>
    </div>
  );
}

export default App;
