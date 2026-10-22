import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RegisterLayoutProvider } from "./components/RegisterLayout";
import { loadTerminal } from "./config/terminal";
import "./index.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Root element is missing.");
}

// The activated store must be known before the app's modules compute their store identity.
void loadTerminal()
  .catch(() => null)
  .then(() => import("./App"))
  .then(({ App }) => {
    createRoot(root).render(
      <StrictMode>
        <RegisterLayoutProvider>
          <App />
        </RegisterLayoutProvider>
      </StrictMode>,
    );
  });
