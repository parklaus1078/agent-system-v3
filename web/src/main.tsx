import { Component, StrictMode, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import './design/tokens.css';
import App from './App';
import { useStore } from './store/useStore';

/** Last-resort guard: a render crash shows a recoverable message instead of a blank page. */
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 24, fontFamily: 'system-ui', color: '#c0392b' }}>
          <h2>화면을 표시하는 중 오류가 발생했습니다.</h2>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{String(this.state.error.message)}</pre>
          <button onClick={() => location.reload()}>새로고침</button>
        </div>
      );
    }
    return this.props.children;
  }
}

// Surface otherwise-silent async failures (e.g. a fire-and-forget API write that rejected).
window.addEventListener('unhandledrejection', (e) => {
  const reason = e.reason;
  useStore.getState().setError(
    `요청 처리 중 오류: ${reason instanceof Error ? reason.message : String(reason)}`,
  );
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
