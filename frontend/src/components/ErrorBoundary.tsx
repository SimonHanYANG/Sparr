import { Component, type ReactNode } from 'react'

/** Catch render errors — show a friendly fallback instead of a white screen. */
export default class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-md pt-24 text-center">
          <p className="text-[15px] font-medium text-ink">页面出错了 / Something went wrong</p>
          <p className="mt-2 text-[12.5px] text-muted">{this.state.error.message}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-5 rounded-full bg-accent px-5 py-2.5 text-[13px] text-white hover:bg-accent-hover"
          >
            刷新页面 / Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
