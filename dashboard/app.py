"""NiceGUI web dashboard for the EV betting system."""

from nicegui import app, ui


def create_dashboard():
    """Create and configure the NiceGUI dashboard."""

    @ui.page("/")
    async def overview():
        with ui.header().classes("bg-dark"):
            ui.label("EV System Dashboard").classes("text-h5")

        with ui.left_drawer().classes("bg-dark"):
            ui.link("Overview", "/").classes("text-white")
            ui.link("Signals", "/signals").classes("text-white")
            ui.link("History", "/history").classes("text-white")
            ui.link("Models", "/models").classes("text-white")
            ui.link("Settings", "/settings").classes("text-white")

        with ui.row().classes("w-full gap-4"):
            with ui.card().classes("w-64"):
                ui.label("Bankroll").classes("text-h6")
                bankroll_label = ui.label("Loading...").classes("text-h4 text-green")
            with ui.card().classes("w-64"):
                ui.label("Today's P&L").classes("text-h6")
                pnl_label = ui.label("Loading...").classes("text-h4")
            with ui.card().classes("w-64"):
                ui.label("Active Signals").classes("text-h6")
                signals_label = ui.label("Loading...").classes("text-h4")
            with ui.card().classes("w-64"):
                ui.label("Drawdown").classes("text-h6")
                drawdown_label = ui.label("Loading...").classes("text-h4")

        async def load_overview_data():
            try:
                from sqlalchemy import func, select

                from db.models.betting import BankrollSnapshot, Bet
                from db.models.predictions import EVSignal
                from db.session import get_session

                async with get_session() as session:
                    # Bankroll
                    result = await session.execute(
                        select(BankrollSnapshot)
                        .order_by(BankrollSnapshot.snapshot_at.desc())
                        .limit(1)
                    )
                    snapshot = result.scalar_one_or_none()
                    if snapshot:
                        bankroll_label.text = f"{snapshot.balance_dkk:,.0f} DKK"
                        drawdown_label.text = f"{snapshot.drawdown_pct:.1%}"
                    else:
                        from config.settings import settings

                        bankroll_label.text = f"{settings.bankroll_dkk:,.0f} DKK"
                        drawdown_label.text = "0.0%"

                    # Active signals
                    sig_result = await session.execute(
                        select(func.count())
                        .select_from(EVSignal)
                        .where(EVSignal.status == "pending")
                    )
                    signals_label.text = str(sig_result.scalar() or 0)

                    # Today's P&L
                    from datetime import date, datetime, timezone

                    today_start = datetime.combine(date.today(), datetime.min.time()).replace(
                        tzinfo=timezone.utc
                    )
                    pnl_result = await session.execute(
                        select(func.coalesce(func.sum(Bet.pnl_dkk), 0.0)).where(
                            Bet.settled_at >= today_start
                        )
                    )
                    today_pnl = pnl_result.scalar() or 0.0
                    pnl_label.text = f"{today_pnl:+,.0f} DKK"
            except Exception:
                bankroll_label.text = "10,000 DKK"
                pnl_label.text = "+0 DKK"
                signals_label.text = "0"
                drawdown_label.text = "0.0%"

        await load_overview_data()

    @ui.page("/signals")
    async def signals_page():
        with ui.header().classes("bg-dark"):
            ui.label("EV System Dashboard").classes("text-h5")

        with ui.left_drawer().classes("bg-dark"):
            ui.link("Overview", "/").classes("text-white")
            ui.link("Signals", "/signals").classes("text-white")
            ui.link("History", "/history").classes("text-white")
            ui.link("Models", "/models").classes("text-white")
            ui.link("Settings", "/settings").classes("text-white")

        ui.label("EV Signals").classes("text-h4")

        columns = [
            {"name": "id", "label": "ID", "field": "id"},
            {"name": "market", "label": "Market", "field": "market"},
            {"name": "selection", "label": "Selection", "field": "selection"},
            {"name": "bookmaker", "label": "Bookmaker", "field": "bookmaker"},
            {"name": "odds", "label": "Odds", "field": "odds"},
            {"name": "ev", "label": "EV %", "field": "ev"},
            {"name": "stake", "label": "Stake DKK", "field": "stake"},
            {"name": "status", "label": "Status", "field": "status"},
        ]
        rows = []

        try:
            from sqlalchemy import select

            from db.models.predictions import EVSignal
            from db.session import get_session

            async with get_session() as session:
                result = await session.execute(
                    select(EVSignal).order_by(EVSignal.generated_at.desc()).limit(50)
                )
                signals = result.scalars().all()
                for s in signals:
                    rows.append(
                        {
                            "id": s.id[:8],
                            "market": s.market,
                            "selection": s.selection,
                            "bookmaker": s.bookmaker,
                            "odds": f"{s.odds_at_signal:.2f}",
                            "ev": f"{s.ev_pct:.1%}",
                            "stake": f"{s.suggested_stake_dkk:.0f}",
                            "status": s.status,
                        }
                    )
        except Exception:
            pass

        ui.table(columns=columns, rows=rows).classes("w-full")

    @ui.page("/history")
    async def history_page():
        with ui.header().classes("bg-dark"):
            ui.label("EV System Dashboard").classes("text-h5")

        with ui.left_drawer().classes("bg-dark"):
            ui.link("Overview", "/").classes("text-white")
            ui.link("Signals", "/signals").classes("text-white")
            ui.link("History", "/history").classes("text-white")
            ui.link("Models", "/models").classes("text-white")
            ui.link("Settings", "/settings").classes("text-white")

        ui.label("Bet History").classes("text-h4")

        columns = [
            {"name": "id", "label": "ID", "field": "id"},
            {"name": "market", "label": "Market", "field": "market"},
            {"name": "selection", "label": "Selection", "field": "selection"},
            {"name": "odds", "label": "Odds", "field": "odds"},
            {"name": "stake", "label": "Stake DKK", "field": "stake"},
            {"name": "outcome", "label": "Outcome", "field": "outcome"},
            {"name": "pnl", "label": "P&L DKK", "field": "pnl"},
        ]
        rows = []

        try:
            from sqlalchemy import select

            from db.models.betting import Bet
            from db.session import get_session

            async with get_session() as session:
                result = await session.execute(
                    select(Bet).order_by(Bet.placed_at.desc()).limit(50)
                )
                bets = result.scalars().all()
                for b in bets:
                    rows.append(
                        {
                            "id": b.id[:8],
                            "market": b.market,
                            "selection": b.selection,
                            "odds": f"{b.odds:.2f}",
                            "stake": f"{b.stake_dkk:.0f}",
                            "outcome": b.outcome or "pending",
                            "pnl": f"{b.pnl_dkk:+.0f}" if b.pnl_dkk is not None else "-",
                        }
                    )
        except Exception:
            pass

        ui.table(columns=columns, rows=rows).classes("w-full")

    @ui.page("/models")
    async def models_page():
        with ui.header().classes("bg-dark"):
            ui.label("EV System Dashboard").classes("text-h5")

        with ui.left_drawer().classes("bg-dark"):
            ui.link("Overview", "/").classes("text-white")
            ui.link("Signals", "/signals").classes("text-white")
            ui.link("History", "/history").classes("text-white")
            ui.link("Models", "/models").classes("text-white")
            ui.link("Settings", "/settings").classes("text-white")

        ui.label("Model Performance").classes("text-h4")

        columns = [
            {"name": "type", "label": "Type", "field": "type"},
            {"name": "version", "label": "Version", "field": "version"},
            {"name": "brier", "label": "Brier Score", "field": "brier"},
            {"name": "log_loss", "label": "Log Loss", "field": "log_loss"},
            {"name": "auc", "label": "AUC-ROC", "field": "auc"},
            {"name": "active", "label": "Active", "field": "active"},
        ]
        rows = []

        try:
            from sqlalchemy import select

            from db.models.system import ModelRun
            from db.session import get_session

            async with get_session() as session:
                result = await session.execute(
                    select(ModelRun).order_by(ModelRun.trained_at.desc())
                )
                models = result.scalars().all()
                for m in models:
                    rows.append(
                        {
                            "type": m.model_type,
                            "version": m.model_version,
                            "brier": f"{m.brier_score:.4f}",
                            "log_loss": f"{m.log_loss:.4f}",
                            "auc": f"{m.auc_roc:.4f}" if m.auc_roc else "-",
                            "active": "Yes" if m.active else "No",
                        }
                    )
        except Exception:
            pass

        ui.table(columns=columns, rows=rows).classes("w-full")

    @ui.page("/settings")
    async def settings_page():
        with ui.header().classes("bg-dark"):
            ui.label("EV System Dashboard").classes("text-h5")

        with ui.left_drawer().classes("bg-dark"):
            ui.link("Overview", "/").classes("text-white")
            ui.link("Signals", "/signals").classes("text-white")
            ui.link("History", "/history").classes("text-white")
            ui.link("Models", "/models").classes("text-white")
            ui.link("Settings", "/settings").classes("text-white")

        ui.label("Settings").classes("text-h4")

        from config.settings import settings

        with ui.card():
            ui.label("Risk Parameters").classes("text-h6")
            ui.number("Min EV Threshold", value=settings.min_ev_threshold * 100, suffix="%")
            ui.number("Kelly Fraction", value=settings.kelly_fraction)
            ui.number("Max Stake %", value=settings.max_stake_pct * 100, suffix="%")
            ui.number("Min Odds", value=settings.min_odds)
            ui.number("Max Odds", value=settings.max_odds)

        with ui.card().classes("mt-4"):
            ui.label("Bankroll Parameters").classes("text-h6")
            ui.number("Bankroll (DKK)", value=settings.bankroll_dkk)
            ui.number("Max Daily Exposure %", value=settings.max_daily_exposure_pct * 100, suffix="%")
            ui.number("Max Fixture Exposure %", value=settings.max_fixture_exposure_pct * 100, suffix="%")
            ui.number("Daily Stop Loss %", value=settings.daily_stop_loss_pct * 100, suffix="%")
            ui.number("Max Drawdown %", value=settings.max_drawdown_pct * 100, suffix="%")


def run_dashboard(port: int = 8080):
    """Run the NiceGUI dashboard."""
    create_dashboard()
    ui.run(port=port, title="EV System", dark=True, reload=False)
