import { applyDocumentLocale, applyTheme, readLocale, readTheme } from "@ai-pos/ui";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.css";
import { applyPrimaryColor, storedPrimaryColor } from "./lib/theme";

applyDocumentLocale(readLocale());
applyTheme(readTheme());
applyPrimaryColor(storedPrimaryColor());

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Root element is missing.");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
