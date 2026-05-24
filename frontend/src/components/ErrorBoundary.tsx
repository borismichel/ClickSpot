import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button, Result } from "antd";

interface Props {
  children: ReactNode;
  /** When this value changes, a captured error is cleared so the subtree can re-render. */
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

/**
 * Contains render-time errors to its subtree so one bad response degrades to an
 * inline error state instead of unmounting the whole SPA (white screen of death).
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught a render error:", error, info.componentStack);
  }

  componentDidUpdate(prevProps: Props) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <Result
          status="error"
          title="Something went wrong on this page"
          subTitle="We couldn't load this page. Reloading usually fixes it — if it keeps happening, the data source may be unavailable."
          extra={
            <Button type="primary" onClick={() => window.location.reload()}>
              Reload page
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
