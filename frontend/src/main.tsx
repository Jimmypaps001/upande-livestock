import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App";
import { dismissSplash } from "./lib/splash";

const el = document.getElementById("livestock-root");
if (el) {
  createRoot(el).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
  // After the first paint, not before it: dismissing on the render call itself
  // uncovers a root React has been handed but has not yet drawn, which is the
  // blank frame the cover exists to hide.
  requestAnimationFrame(() => requestAnimationFrame(dismissSplash));
}
