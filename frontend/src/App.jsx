import { useEffect, useMemo, useState } from "react";

import GeneratorPage from "./pages/GeneratorPage";
import PostprocessPage from "./pages/PostprocessPage";
import WizardPage from "./pages/WizardPage";

function getCurrentRoute() {
  const hash = window.location.hash || "#/wizard";

  if (hash.startsWith("#/advanced/postprocess")) {
    return { main: "advanced", sub: "postprocess" };
  }

  if (hash.startsWith("#/advanced")) {
    return { main: "advanced", sub: "generate" };
  }

  return { main: "wizard", sub: "wizard" };
}

function App() {
  const [route, setRoute] = useState(getCurrentRoute());

  useEffect(() => {
    const onHashChange = () => setRoute(getCurrentRoute());
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) window.location.hash = "#/wizard";
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const title = useMemo(() => {
    if (route.main === "advanced" && route.sub === "postprocess") return "高级模式 / 后处理";
    if (route.main === "advanced") return "高级模式 / 生成";
    return "海报向导";
  }, [route.main, route.sub]);

  return (
    <div>
      <header className="top-nav">
        <div className="top-nav-inner">
          <strong>AI Poster Studio</strong>

          <nav className="top-nav-links">
            <a href="#/wizard" className={route.main === "wizard" ? "active" : ""}>
              海报向导
            </a>
            <a href="#/advanced/generate" className={route.main === "advanced" ? "active" : ""}>
              高级模式
            </a>
          </nav>

          {route.main === "advanced" ? (
            <nav className="top-nav-links top-nav-sub-links">
              <a
                href="#/advanced/generate"
                className={route.sub === "generate" ? "active" : ""}
              >
                生成页
              </a>
              <a
                href="#/advanced/postprocess"
                className={route.sub === "postprocess" ? "active" : ""}
              >
                后处理页
              </a>
            </nav>
          ) : null}

          <small>{title}</small>
        </div>
      </header>

      {route.main === "wizard" ? <WizardPage /> : null}
      {route.main === "advanced" && route.sub === "generate" ? <GeneratorPage /> : null}
      {route.main === "advanced" && route.sub === "postprocess" ? <PostprocessPage /> : null}
    </div>
  );
}

export default App;
