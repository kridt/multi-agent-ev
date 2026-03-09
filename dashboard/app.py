"""
EV Betting Dashboard — entry point.

Starts the FastAPI + WebSocket server using uvicorn.

ASSUMPTIONS (all explicit):
- This module is the sole entry point for the dashboard process.
- uvicorn is configured with log_level="info" so its access logs appear in
  the same stream as application logs.
- The previous NiceGUI implementation (create_dashboard / ui.run) has been
  replaced. NiceGUI is no longer used by this module.
- Host 0.0.0.0 binds to all interfaces. Override via the 'host' parameter
  if binding to a specific interface is required.
"""

import logging

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def run_dashboard(host: str = "0.0.0.0", port: int = 8080) -> None:
    """
    Run the real-time EV dashboard.

    Imports the FastAPI app from dashboard.api and hands it to uvicorn.
    The scanner background task is managed by the FastAPI lifespan defined
    in dashboard.api — no explicit scanner setup is required here.

    Parameters
    ----------
    host:
        Network interface to bind to. Default "0.0.0.0" (all interfaces).
    port:
        TCP port to listen on. Default 8080.
    """
    from dashboard.api import app

    logger.info("Starting EV Dashboard on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_dashboard()
