"""Reusable Plotly chart builders for dashboard pages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd
import plotly.graph_objects as go


COLORS = ["#2463a2", "#d55e00", "#009e73", "#cc79a7", "#56b4e9", "#e69f00", "#0072b2", "#7a5195"]


def _finish(
    figure: go.Figure,
    title: str,
    x_title: str,
    y_title: str,
    *,
    height: int = 450,
) -> go.Figure:
    """Apply a consistent research-dashboard layout."""

    figure.update_layout(
        title={"text": title, "x": 0.02, "xanchor": "left"},
        xaxis_title=x_title,
        yaxis_title=y_title,
        hovermode="x unified",
        legend_title_text="",
        template="plotly_white",
        height=height,
        margin={"l": 45, "r": 25, "t": 70, "b": 45},
    )
    return figure


def _empty_figure(title: str, message: str = "표시할 유효 데이터가 없습니다.") -> go.Figure:
    """Return a valid Figure with a user-facing empty-state annotation."""

    figure = go.Figure()
    figure.add_annotation(text=message, x=0.5, y=0.5, showarrow=False)
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return _finish(figure, title, "", "")


def create_timeseries_chart(
    dataframe: pd.DataFrame,
    x_column: str,
    y_columns: str | Sequence[str],
    *,
    title: str,
    y_title: str,
    color_column: str | None = None,
    labels: Mapping[str, str] | None = None,
) -> go.Figure:
    """Create an interactive line chart for one/many values or city groups."""

    values = [y_columns] if isinstance(y_columns, str) else list(y_columns)
    labels = labels or {}
    figure = go.Figure()
    if color_column:
        if not values:
            return _empty_figure(title)
        y_column = values[0]
        clean = dataframe.dropna(subset=[x_column, y_column, color_column])
        for index, (name, group) in enumerate(clean.groupby(color_column, sort=False)):
            group = group.sort_values(x_column)
            figure.add_trace(
                go.Scatter(
                    x=group[x_column],
                    y=group[y_column],
                    name=str(name),
                    mode="lines",
                    line={"width": 2, "color": COLORS[index % len(COLORS)]},
                    hovertemplate=f"%{{x}}<br>{name}: %{{y:.3f}}<extra></extra>",
                )
            )
    else:
        for index, value_column in enumerate(values):
            if value_column not in dataframe.columns:
                continue
            clean = dataframe.dropna(subset=[x_column, value_column]).sort_values(x_column)
            if clean.empty:
                continue
            figure.add_trace(
                go.Scatter(
                    x=clean[x_column],
                    y=clean[value_column],
                    name=labels.get(value_column, value_column),
                    mode="lines",
                    line={"width": 2, "color": COLORS[index % len(COLORS)]},
                    hovertemplate="%{x}<br>%{y:.3f}<extra>%{fullData.name}</extra>",
                )
            )
    if not figure.data:
        return _empty_figure(title)
    return _finish(figure, title, "연도", y_title)


def create_climatology_chart(
    dataframe: pd.DataFrame,
    value_column: str,
    *,
    title: str,
    y_title: str,
) -> go.Figure:
    """Create a monthly climatology line chart."""

    figure = create_timeseries_chart(
        dataframe,
        "MONTH",
        value_column,
        title=title,
        y_title=y_title,
        color_column="city" if "city" in dataframe and dataframe["city"].nunique() > 1 else None,
        labels={value_column: "월 climatology"},
    )
    figure.update_xaxes(tickmode="array", tickvals=list(range(1, 13)))
    figure.update_layout(xaxis_title="월")
    return figure


def create_anomaly_chart(
    dataframe: pd.DataFrame,
    anomaly_column: str,
    *,
    title: str,
    unit: str,
) -> go.Figure:
    """Create a signed anomaly chart, using bars for one city and lines for many."""

    clean = dataframe.dropna(subset=["YEAR", anomaly_column]).sort_values("YEAR")
    if clean.empty:
        return _empty_figure(title)
    figure = go.Figure()
    if "city" in clean.columns and clean["city"].nunique() > 1:
        for index, (city, group) in enumerate(clean.groupby("city", sort=False)):
            figure.add_trace(
                go.Scatter(
                    x=group["YEAR"], y=group[anomaly_column], name=str(city),
                    mode="lines", line={"color": COLORS[index % len(COLORS)]},
                    hovertemplate="%{x}<br>%{y:+.3f}<extra>%{fullData.name}</extra>",
                )
            )
    else:
        colors = ["#d55e00" if value >= 0 else "#2463a2" for value in clean[anomaly_column]]
        figure.add_trace(
            go.Bar(
                x=clean["YEAR"], y=clean[anomaly_column], marker_color=colors,
                name="Anomaly", hovertemplate="%{x}<br>%{y:+.3f}<extra></extra>",
            )
        )
        figure.add_hline(y=0, line_width=1, line_color="#555")
    return _finish(figure, title, "연도", f"Anomaly ({unit})")


def create_trend_bar_chart(
    dataframe: pd.DataFrame,
    *,
    category_column: str = "city",
    value_column: str = "sen_slope_per_decade",
    title: str,
    y_title: str,
) -> go.Figure:
    """Create a city/metric trend comparison bar chart."""

    clean = dataframe.dropna(subset=[category_column, value_column]).sort_values(value_column)
    if clean.empty:
        return _empty_figure(title)
    colors = ["#d55e00" if value >= 0 else "#2463a2" for value in clean[value_column]]
    figure = go.Figure(
        go.Bar(
            x=clean[category_column], y=clean[value_column], marker_color=colors,
            hovertemplate="%{x}<br>%{y:+.3f}<extra></extra>",
        )
    )
    figure.add_hline(y=0, line_width=1, line_color="#555")
    return _finish(figure, title, "", y_title)


def create_heatmap(
    dataframe: pd.DataFrame,
    *,
    row_column: str,
    column_column: str,
    value_column: str,
    title: str,
    colorbar_title: str,
    colorscale: str = "RdBu_r",
    zmid: float | None = 0.0,
) -> go.Figure:
    """Create an interactive pivoted heatmap."""

    clean = dataframe.dropna(subset=[row_column, column_column, value_column])
    if clean.empty:
        return _empty_figure(title)
    pivot = clean.pivot_table(
        index=row_column, columns=column_column, values=value_column, aggfunc="first", dropna=False
    )
    if pivot.empty:
        return _empty_figure(title)
    heatmap_kwargs: dict[str, object] = {
        "z": pivot.to_numpy(),
        "x": [str(value) for value in pivot.columns],
        "y": [str(value) for value in pivot.index],
        "colorscale": colorscale,
        "colorbar": {"title": colorbar_title},
        "hovertemplate": f"{row_column}: %{{y}}<br>{column_column}: %{{x}}<br>값: %{{z:.3f}}<extra></extra>",
    }
    if zmid is not None:
        heatmap_kwargs["zmid"] = zmid
    figure = go.Figure(go.Heatmap(**heatmap_kwargs))
    return _finish(figure, title, column_column, row_column, height=500)


def create_sen_slope_ci_chart(
    dataframe: pd.DataFrame,
    *,
    title: str,
    unit: str,
) -> go.Figure:
    """Create Sen's slope points with asymmetric 95% confidence intervals."""

    needed = ["city", "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper"]
    clean = dataframe.dropna(subset=needed).sort_values("sen_slope_per_decade")
    if clean.empty:
        return _empty_figure(title, "Sen's slope 또는 confidence interval 자료가 없습니다.")
    center = clean["sen_slope_per_decade"]
    figure = go.Figure(
        go.Scatter(
            x=center,
            y=clean["city"],
            mode="markers",
            marker={"size": 9, "color": "#2463a2"},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": clean["sen_ci_upper"] - center,
                "arrayminus": center - clean["sen_ci_lower"],
            },
            hovertemplate="%{y}<br>Sen slope: %{x:+.3f}<extra></extra>",
        )
    )
    figure.add_vline(x=0, line_width=1, line_dash="dash", line_color="#555")
    return _finish(figure, title, f"Sen's slope ({unit}/10년)", "도시")


def create_seasonal_chart(
    dataframe: pd.DataFrame,
    *,
    title: str,
    unit: str,
    category_column: str = "city",
) -> go.Figure:
    """Create grouped seasonal Sen-slope bars."""

    clean = dataframe.dropna(subset=[category_column, "season", "sen_slope_per_decade"])
    if clean.empty:
        return _empty_figure(title)
    figure = go.Figure()
    for index, (season, group) in enumerate(clean.groupby("season", sort=False)):
        figure.add_trace(
            go.Bar(
                x=group[category_column], y=group["sen_slope_per_decade"], name=str(season),
                marker_color=COLORS[index % len(COLORS)],
                hovertemplate="%{x}<br>%{y:+.3f}<extra>%{fullData.name}</extra>",
            )
        )
    figure.add_hline(y=0, line_width=1, line_color="#555")
    figure.update_layout(barmode="group")
    return _finish(figure, title, "", f"Sen's slope ({unit}/10년)")


def create_slope_comparison_scatter(
    dataframe: pd.DataFrame,
    *,
    title: str,
) -> go.Figure:
    """Compare linear and Sen slopes without combining their meanings."""

    clean = dataframe.dropna(subset=["linear_slope_per_decade", "sen_slope_per_decade", "city"])
    if clean.empty:
        return _empty_figure(title)
    figure = go.Figure(
        go.Scatter(
            x=clean["linear_slope_per_decade"],
            y=clean["sen_slope_per_decade"],
            mode="markers+text",
            text=clean["city"],
            textposition="top center",
            marker={"size": 9, "color": "#2463a2"},
            customdata=clean.get("metric"),
            hovertemplate="%{text}<br>Linear: %{x:+.3f}<br>Sen: %{y:+.3f}<extra></extra>",
        )
    )
    lows = pd.concat([clean["linear_slope_per_decade"], clean["sen_slope_per_decade"]])
    low, high = float(lows.min()), float(lows.max())
    figure.add_shape(type="line", x0=low, x1=high, y0=low, y1=high, line={"dash": "dash", "color": "#888"})
    return _finish(figure, title, "Linear slope / 10년", "Sen's slope / 10년")


def create_location_map(dataframe: pd.DataFrame, *, title: str) -> go.Figure:
    """Create a simple geographic location view without external map tokens."""

    clean = dataframe.dropna(subset=["city", "latitude", "longitude"])
    if clean.empty:
        return _empty_figure(title)
    figure = go.Figure(
        go.Scattergeo(
            lon=clean["longitude"], lat=clean["latitude"], text=clean["city"],
            mode="markers+text", textposition="top center",
            textfont={"color": "#111827"},
            marker={"size": 10, "color": "#2463a2"},
            hovertemplate="%{text}<br>%{lat:.4f}, %{lon:.4f}<extra></extra>",
        )
    )
    figure.update_geos(
        projection_type="mercator",
        lonaxis_range=[124.5, 130.5],
        lataxis_range=[32.5, 38.8],
        showcountries=True,
        showcoastlines=True,
        showland=True,
        landcolor="#f3f4f6",
        fitbounds=False,
    )
    figure.update_layout(
        title={"text": title, "x": 0.02}, template="plotly_white", height=470,
        margin={"l": 10, "r": 10, "t": 60, "b": 10},
    )
    return figure


def create_validation_scatter(
    dataframe: pd.DataFrame,
    nasa_column: str,
    kma_column: str,
    *,
    title: str,
    unit: str,
) -> go.Figure:
    """Create an interactive NASA-vs-KMA scatter with a 1:1 reference line."""

    clean = dataframe.dropna(subset=[nasa_column, kma_column])
    if clean.empty:
        return _empty_figure(title, "선택 조건에 유효한 NASA-KMA pair가 없습니다.")
    figure = go.Figure(
        go.Scattergl(
            x=clean[kma_column],
            y=clean[nasa_column],
            mode="markers",
            marker={"size": 5, "opacity": 0.28, "color": "#2463a2"},
            hovertemplate=f"KMA: %{{x:.3f}} {unit}<br>NASA: %{{y:.3f}} {unit}<extra></extra>",
        )
    )
    lower = float(min(clean[kma_column].min(), clean[nasa_column].min()))
    upper = float(max(clean[kma_column].max(), clean[nasa_column].max()))
    figure.add_shape(
        type="line",
        x0=lower,
        x1=upper,
        y0=lower,
        y1=upper,
        line={"dash": "dash", "color": "#555"},
    )
    return _finish(figure, title, f"KMA ASOS ({unit})", f"NASA POWER ({unit})")


def create_validation_annual_comparison(
    dataframe: pd.DataFrame,
    nasa_column: str,
    kma_column: str,
    *,
    title: str,
    unit: str,
) -> go.Figure:
    """Create annual means from stored daily matched values for both sources."""

    clean = dataframe.copy()
    clean["year"] = pd.to_datetime(clean["date"], errors="coerce").dt.year
    annual = clean.groupby("year")[[nasa_column, kma_column]].mean(numeric_only=True).reset_index()
    return create_timeseries_chart(
        annual,
        "year",
        [nasa_column, kma_column],
        title=title,
        y_title=unit,
        labels={nasa_column: "NASA POWER", kma_column: "KMA ASOS"},
    )
