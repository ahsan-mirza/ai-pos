import { applyDocumentLocale } from "@ai-pos/ui";
import { MotionConfig } from "framer-motion";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../index.css";
import { Home3Page } from "./Home3Page";
import "./home3.css";

applyDocumentLocale("en");

const root = document.getElementById("root");
if (root === null) throw new Error("Root element is missing.");

createRoot(root).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <Home3Page />
    </MotionConfig>
  </StrictMode>,
);
