import { MotionConfig } from "framer-motion";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../index.css";
import { Home2Page } from "./Home2Page";
import "./home2.css";

const root = document.getElementById("root");
if (root === null) throw new Error("Root element is missing.");

createRoot(root).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <Home2Page />
    </MotionConfig>
  </StrictMode>,
);
