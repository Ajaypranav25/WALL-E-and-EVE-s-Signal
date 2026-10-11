import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { RunProvider } from "./lib/store";
import "./styles/theme.css";
import "./styles/app.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing from app.html");

createRoot(root).render(
  <StrictMode>
    <RunProvider>
      <App />
    </RunProvider>
  </StrictMode>,
);
