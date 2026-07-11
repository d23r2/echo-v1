import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { ConversationsProvider } from "./state/conversationsContext";
import { RoleProvider } from "./state/roleContext";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RoleProvider>
      <ConversationsProvider>
        <App />
      </ConversationsProvider>
    </RoleProvider>
  </React.StrictMode>
);
