"""Reusable Plotly chart components for the dashboard."""
from __future__ import annotations


import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_rolling_volatility(
    vol_df: pd.DataFrame,
    symbol: str,
    window: int = 21,
) -> go.Figure:
    """Line chart of rolling annualised volatility over time."""
    vol_col = f"rolling_vol_{window}d"
    if vol_df.empty or vol_col not in vol_df.columns:
        return _empty_figure(f"No volatility data for {symbol}")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=vol_df.index,
            y=vol_df[vol_col] * 100,
            mode="lines",
            name=f"{window}-day Rolling Vol (%)",
            line=dict(color="#2563EB", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(37,99,235,0.1)",
        )
    )
    fig.update_layout(
        title=f"{symbol} — {window}-Day Rolling Volatility (Annualised)",
        xaxis_title="Date",
        yaxis_title="Volatility (%)",
        height=350,
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def plot_price_chart(
    prices_df: pd.DataFrame,
    symbol: str,
    show_volume: bool = True,
) -> go.Figure:
    """Candlestick chart with optional volume subplot."""
    if prices_df.empty:
        return _empty_figure(f"No price data for {symbol}")

    has_ohlc = all(c in prices_df.columns for c in ["open", "high", "low", "close"])

    if show_volume and "volume" in prices_df.columns:
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.75, 0.25],
            vertical_spacing=0.03,
        )
        row_price = 1
        add_volume = True
    else:
        fig = make_subplots(rows=1, cols=1)
        row_price = 1
        add_volume = False

    if has_ohlc:
        fig.add_trace(
            go.Candlestick(
                x=prices_df.index,
                open=prices_df["open"],
                high=prices_df["high"],
                low=prices_df["low"],
                close=prices_df["close"],
                name="OHLC",
                increasing_line_color="#16A34A",
                decreasing_line_color="#DC2626",
            ),
            row=row_price, col=1,
        )
    else:
        col = "adj_close" if "adj_close" in prices_df.columns else "close"
        fig.add_trace(
            go.Scatter(
                x=prices_df.index,
                y=prices_df[col],
                mode="lines",
                name="Adj Close",
                line=dict(color="#2563EB", width=1.5),
            ),
            row=row_price, col=1,
        )

    if add_volume:
        fig.add_trace(
            go.Bar(
                x=prices_df.index,
                y=prices_df["volume"],
                name="Volume",
                marker_color="rgba(107,114,128,0.5)",
            ),
            row=2, col=1,
        )

    fig.update_layout(
        title=f"{symbol} — Price Chart",
        xaxis_rangeslider_visible=False,
        height=500,
        template="plotly_white",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def plot_momentum_bar(
    rankings_df: pd.DataFrame,
    top_n: int = 20,
    bottom_n: int = 20,
    mode: str = "top",
) -> go.Figure:
    """Horizontal bar chart for top/bottom momentum symbols."""
    if rankings_df.empty or "momentum_score" not in rankings_df.columns:
        return _empty_figure("No ranking data available")

    valid = rankings_df.dropna(subset=["momentum_score"]).copy()
    valid["momentum_pct"] = valid["momentum_score"] * 100

    if mode == "top":
        subset = valid.nsmallest(top_n, "momentum_rank")
        title = f"Top {top_n} Momentum Stocks"
        color = "#16A34A"
    else:
        subset = valid.nlargest(bottom_n, "momentum_rank")
        title = f"Bottom {bottom_n} Momentum Stocks"
        color = "#DC2626"

    subset = subset.sort_values("momentum_pct", ascending=(mode != "top"))

    fig = go.Figure(
        go.Bar(
            x=subset["momentum_pct"],
            y=subset["symbol"],
            orientation="h",
            marker_color=color,
            text=subset["momentum_pct"].map("{:.1f}%".format),
            textposition="outside",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Momentum Score (%)",
        yaxis_title="Symbol",
        height=max(350, top_n * 25),
        template="plotly_white",
        margin=dict(l=80, r=80, t=50, b=40),
    )
    return fig


def plot_sector_heatmap(
    rankings_df: pd.DataFrame,
    metric: str = "momentum_score",
) -> go.Figure:
    """Sector-aggregated heatmap for a given metric."""
    required = {"sector", metric}
    if rankings_df.empty or not required.issubset(rankings_df.columns):
        return _empty_figure("Insufficient data for heatmap")

    agg = (
        rankings_df.dropna(subset=[metric, "sector"])
        .groupby("sector")[metric]
        .agg(["mean", "count"])
        .reset_index()
    )
    agg.columns = ["sector", "mean_value", "count"]
    agg = agg.sort_values("mean_value", ascending=True)

    metric_label = {
        "momentum_score": "Avg Momentum Score",
        "annualized_volatility": "Avg Ann. Volatility",
        "return_1y": "Avg 1Y Return",
        "return_6m": "Avg 6M Return",
    }.get(metric, metric)

    fig = go.Figure(
        go.Bar(
            x=agg["mean_value"] * 100,
            y=agg["sector"],
            orientation="h",
            text=agg["count"].map("n={}".format),
            textposition="inside",
            marker=dict(
                color=agg["mean_value"],
                colorscale="RdYlGn",
                showscale=True,
                colorbar=dict(title=metric_label),
            ),
        )
    )
    fig.update_layout(
        title=f"Sector {metric_label}",
        xaxis_title=f"{metric_label} (%)",
        height=max(300, len(agg) * 35),
        template="plotly_white",
        margin=dict(l=180, r=20, t=50, b=40),
    )
    return fig


def plot_volatility_comparison(
    vol_data: dict[str, pd.Series],
    window: int = 21,
) -> go.Figure:
    """Overlaid rolling volatility for multiple symbols."""
    if not vol_data:
        return _empty_figure("No volatility data available")

    fig = go.Figure()
    for symbol, series in vol_data.items():
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series * 100,
                mode="lines",
                name=symbol,
                line=dict(width=1.5),
            )
        )

    fig.update_layout(
        title=f"{window}-Day Rolling Volatility Comparison (Annualised)",
        xaxis_title="Date",
        yaxis_title="Volatility (%)",
        height=400,
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color="gray"),
    )
    fig.update_layout(
        template="plotly_white",
        height=300,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig
