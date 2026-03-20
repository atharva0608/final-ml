import React from 'react';

/**
 * ErrorBoundary — Issue #29
 * Catches render errors in child trees and shows a fallback UI with Retry.
 * Wrap independent dashboard panels so one crash doesn't blank the entire page.
 *
 * Usage:
 *   <ErrorBoundary label="Fleet Overview">
 *     <FleetTable />
 *   </ErrorBoundary>
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', this.props.label || 'Panel', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '16px 20px',
          borderRadius: 8,
          border: '1px solid #fecaca',
          background: '#fef2f2',
          color: '#dc2626',
          fontSize: 13,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}>
          <span style={{ fontWeight: 600 }}>
            {this.props.label || 'Panel'} failed to render.
          </span>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              fontSize: 12,
              padding: '4px 10px',
              borderRadius: 6,
              border: '1px solid #fca5a5',
              background: '#fff',
              color: '#dc2626',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
