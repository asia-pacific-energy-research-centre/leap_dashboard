import plotly.graph_objects as go

from codebase.common_esto_dashboard_renderer import apply_chart_chrome


def test_comparison_totals_use_color_independent_line_and_marker_styles() -> None:
    figure = go.Figure(
        [
            go.Scatter(
                x=[2022, 2023],
                y=[-10.0, -11.0],
                mode="lines",
                stackgroup="fuel",
                name="06.01 Crude oil",
            ),
            go.Scatter(x=[2022, 2023], y=[-10.0, -11.0], mode="lines", name="LEAP Target total"),
            go.Scatter(x=[2022, 2023], y=[-9.0, -9.5], mode="lines", name="ESTO Historical total"),
            go.Scatter(x=[2022, 2023], y=[-10.5, -12.0], mode="lines", name="9th Target total"),
        ]
    )

    apply_chart_chrome(figure, code_axis="product")

    totals = {trace.name: trace for trace in figure.data if not trace.stackgroup}
    leap = totals["LEAP Target total"]
    esto = totals["ESTO Historical total"]
    ninth = totals["9th Target total"]

    assert leap.mode == "lines+markers"
    assert leap.line.dash == "dash"
    assert leap.marker.symbol == "diamond"
    assert leap.marker.line.color == "#ffffff"
    assert leap.marker.line.width >= 1.5
    assert leap.marker.size >= 6
    assert esto.line.dash == "dot"
    assert esto.marker.symbol == "circle"
    assert ninth.line.dash == "dashdot"
    assert ninth.marker.symbol == "square"
