import { Component, type ErrorInfo, type ReactNode } from "react";

type DrawerErrorBoundaryProps = {
  children: ReactNode;
  onClose: () => void;
  resetKey: string;
  title: string;
};

type DrawerErrorBoundaryState = {
  hasError: boolean;
  errorMessage: string | null;
};

export class DrawerErrorBoundary extends Component<
  DrawerErrorBoundaryProps,
  DrawerErrorBoundaryState
> {
  state: DrawerErrorBoundaryState = {
    hasError: false,
    errorMessage: null,
  };

  static getDerivedStateFromError(): DrawerErrorBoundaryState {
    return { hasError: true, errorMessage: null };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`${this.props.title} drawer crashed`, error, errorInfo);
    this.setState({ errorMessage: error instanceof Error ? error.message : String(error) });
  }

  componentDidUpdate(prevProps: DrawerErrorBoundaryProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, errorMessage: null });
    }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="settings-backdrop" role="presentation" onClick={this.props.onClose}>
        <aside
          aria-modal="true"
          className="settings-drawer system-settings-drawer"
          role="dialog"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="modal-header">
            <div className="modal-title-group">
              <p className="panel-kicker">{this.props.title}</p>
              <h2>Errore pannello</h2>
              <p className="modal-copy">
                Il pannello si e chiuso per un errore runtime. Chiudilo e riaprilo senza
                ricaricare tutta la dashboard.
              </p>
            </div>
            <button className="icon-button" type="button" onClick={this.props.onClose}>
              Chiudi
            </button>
          </div>
          <div className="settings-content">
            <div className="panel-state panel-state--error">
              Si e verificato un errore nel pannello. La dashboard principale resta comunque
              operativa.
            </div>
            {this.state.errorMessage ? (
              <div className="panel-state panel-state--error">
                Dettaglio runtime: {this.state.errorMessage}
              </div>
            ) : null}
          </div>
        </aside>
      </div>
    );
  }
}
