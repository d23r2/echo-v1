import { Component, ErrorInfo, ReactNode } from "react";
import { logger } from "../lib/logger";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * ECHO Layer 0 — global error boundary. Without this, a render error
 * anywhere in the tree (e.g. a stale module reference during a dev-server
 * HMR reload) produces a blank white screen with no way back except a hard
 * reload — exactly what happened during this repo's own Cognitive Core
 * verification pass. Catches render errors only (not async/event-handler
 * errors, which is a React limitation, not something skippable here) and
 * shows a clean recovery option instead — never a raw stack trace.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Full detail stays in the console only (a developer tool), never
    // rendered into the page itself.
    logger.error("Unhandled render error", error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-zinc-950 p-6 text-center text-zinc-100">
          <div className="text-4xl">🩹</div>
          <h1 className="text-lg font-semibold">Something went wrong.</h1>
          <p className="max-w-sm text-sm text-zinc-400">
            ECHO hit an unexpected error while rendering. Your data is safe — reloading usually fixes this.
          </p>
          <button
            onClick={this.handleReload}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-zinc-950"
          >
            Reload ECHO
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
