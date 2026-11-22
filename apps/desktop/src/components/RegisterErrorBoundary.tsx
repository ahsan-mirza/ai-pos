import { Component, type ErrorInfo, type ReactNode } from "react";

/** Shown when a screen throws. A blank document is what the native WebView paints if React unmounts the root. */
export function RegisterFailure({ message }: { message: string }) {
  return (
    <div className="flex h-screen items-center justify-center bg-surface p-6 text-charcoal">
      <div className="max-w-lg rounded-3xl bg-white p-8 ring-1 ring-zinc-200">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Register</p>
        <h1 className="mt-2 text-2xl font-semibold">This screen stopped</h1>
        <p className="mt-3 text-sm leading-relaxed">{message}</p>
        <button type="button" className="mt-6 min-h-12 rounded-xl bg-primary px-4 font-semibold text-white" onClick={() => window.location.reload()}>
          Reload register
        </button>
      </div>
    </div>
  );
}

interface BoundaryState {
  message: string | null;
}

export class RegisterErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  override state: BoundaryState = { message: null };

  static getDerivedStateFromError(error: unknown): BoundaryState {
    const message = error instanceof Error && error.message !== "" ? error.message : "The register screen stopped.";
    return { message };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error("register screen stopped", error, info.componentStack);
  }

  override render(): ReactNode {
    if (this.state.message !== null) return <RegisterFailure message={this.state.message} />;
    return this.props.children;
  }
}
