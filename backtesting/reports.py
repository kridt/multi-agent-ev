"""Rich-formatted backtest reporting."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backtesting.metrics import BacktestMetrics


class BacktestReporter:
    """Pretty-print backtest results using Rich."""

    def __init__(self) -> None:
        self.console = Console()

    def print_summary(self, metrics: BacktestMetrics) -> None:
        """Print a Rich-formatted summary of backtest results."""
        table = Table(title="Backtest Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Bets", str(metrics.total_bets))
        table.add_row("Wins", str(metrics.wins))
        table.add_row("Losses", str(metrics.losses))
        table.add_row("Win Rate", f"{metrics.win_rate:.1%}")
        table.add_row("ROI", f"{metrics.roi_pct:.2%}")
        table.add_row("Total Staked", f"{metrics.total_staked:,.0f} DKK")
        table.add_row("Total Return", f"{metrics.total_return:,.0f} DKK")
        table.add_row("Profit", f"{metrics.profit:,.0f} DKK")
        table.add_row("Max Drawdown", f"{metrics.max_drawdown_pct:.1%}")
        table.add_row("Sharpe Ratio", f"{metrics.sharpe_ratio:.2f}")
        table.add_row("Brier Score", f"{metrics.brier_score:.4f}")
        table.add_row("CLV %", f"{metrics.clv_pct:.1%}")
        table.add_row("Avg Odds", f"{metrics.avg_odds:.2f}")
        table.add_row("Avg EV", f"{metrics.avg_ev:.1%}")
        table.add_row("Longest Winning Streak", str(metrics.longest_winning_streak))
        table.add_row("Longest Losing Streak", str(metrics.longest_losing_streak))

        self.console.print(table)

        # Go-live criteria check
        criteria = metrics.meets_go_live()
        lines = []
        for key, passed in criteria.items():
            marker = "PASS" if passed else "FAIL"
            lines.append(f"[{'green' if passed else 'red'}]{marker}[/] - {key}")
        panel_text = "\n".join(lines)
        color = "green" if all(criteria.values()) else "red"
        self.console.print(
            Panel(panel_text, title="Go-Live Criteria", border_style=color)
        )

    def print_equity_curve(self, equity_curve: list[float]) -> None:
        """Print ASCII equity curve using Rich.

        Renders a simple sparkline-style chart showing bankroll evolution.
        """
        if len(equity_curve) < 2:
            self.console.print("[dim]Not enough data for equity curve.[/dim]")
            return

        min_val = min(equity_curve)
        max_val = max(equity_curve)
        val_range = max_val - min_val

        if val_range == 0:
            self.console.print("[dim]Flat equity curve (no variation).[/dim]")
            return

        # Determine chart dimensions
        chart_width = min(80, len(equity_curve))
        chart_height = 15
        blocks = " _.-~^"

        # Downsample equity curve if needed
        if len(equity_curve) > chart_width:
            step = len(equity_curve) / chart_width
            sampled = [
                equity_curve[int(i * step)]
                for i in range(chart_width)
            ]
        else:
            sampled = equity_curve

        # Build rows top-down
        rows: list[str] = []
        for row in range(chart_height, 0, -1):
            threshold = min_val + (row / chart_height) * val_range
            line = ""
            for val in sampled:
                if val >= threshold:
                    line += "#"
                else:
                    line += " "
            label = f"{threshold:>10,.0f} |"
            rows.append(f"{label}{line}")

        # Bottom axis
        bottom_label = f"{min_val:>10,.0f} |"
        rows.append(bottom_label + "-" * len(sampled))

        self.console.print(
            Panel(
                "\n".join(rows),
                title="Equity Curve",
                border_style="blue",
            )
        )

        # Summary line
        start_val = equity_curve[0]
        end_val = equity_curve[-1]
        change = end_val - start_val
        change_pct = change / start_val * 100 if start_val > 0 else 0.0
        color = "green" if change >= 0 else "red"
        self.console.print(
            f"  Start: {start_val:,.0f} DKK -> End: {end_val:,.0f} DKK "
            f"([{color}]{change:+,.0f} DKK / {change_pct:+.1f}%[/])"
        )
