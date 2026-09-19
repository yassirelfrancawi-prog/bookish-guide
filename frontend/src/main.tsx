import React from "react";
import { createRoot } from "react-dom/client";
import { AppRoot } from "@telegram-apps/telegram-ui";
import "@telegram-apps/telegram-ui/dist/styles.css";
import "./index.css";
import { App } from "./App";

// Si on tourne dans Telegram : signaler prêt et étendre la WebApp.
window.Telegram?.WebApp?.ready();
window.Telegram?.WebApp?.expand();

// Apparence : suit Telegram si dispo, sinon dark (fond uniforme, plus joli en local).
const apparence =
  (window.Telegram?.WebApp?.colorScheme as "light" | "dark" | undefined) || "dark";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppRoot appearance={apparence} platform="base">
      <App />
    </AppRoot>
  </React.StrictMode>,
);
