import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import "./index.css";
import { ConversationsProvider } from "./state/conversationsContext";
import { RoleProvider } from "./state/roleContext";
import { TesterProvider } from "./state/testerContext";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <TesterProvider>
        <RoleProvider>
          <ConversationsProvider>
            <App />
          </ConversationsProvider>
        </RoleProvider>
      </TesterProvider>
    </ErrorBoundary>
  </React.StrictMode>
);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((err) => {
      console.error("[sw] registration failed", err);
    });
  });
}
