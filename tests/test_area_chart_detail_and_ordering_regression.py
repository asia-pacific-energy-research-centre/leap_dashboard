
from __future__ import annotations
import pandas as pd
import pytest
from codebase import common_esto_dashboard_renderer as renderer

def _make_spec(flow_boundary: str, flow_label: str, *, configured_groups: list[dict[str, str]] | None = None, preferred_detail: list[str] | None = None) -> dict[str, object]:
    spec = {
        'aggregate_flow_prefix': flow_boundary,
        'aggregate_flow_label': flow_label,
        'source_flow_labels': [flow_label],
        'explicit_flow_boundary': True,
    }
    if configured_groups is not None:
        spec['configured_flow_groups'] = configured_groups
        spec['retain_parent_as_configured_flow_group'] = True
    if preferred_detail is not None:
        spec['preferred_detail_flow_boundaries'] = preferred_detail
    return spec

def test_historical_flow_detail_harmonizes_to_unsplit_leap_parent() -> None:
    rows = pd.DataFrame([
        {'source_system': 'ESTO_EXTENDED', 'scenario': 'historical', 'year': 2022, 'common_flow_code': '16.01.01', 'common_flow_label': '16.01.01 Datacentres', 'common_product_code': '17', 'common_product_label': '17 Electricity', '_configured_flow_group_label': '16.01.01 Datacentres', 'value': 20.0},
        {'source_system': 'ESTO_EXTENDED', 'scenario': 'historical', 'year': 2022, 'common_flow_code': '16.01.99', 'common_flow_label': '16.01.99 Commercial and public services unallocated', 'common_product_code': '17', 'common_product_label': '17 Electricity', '_configured_flow_group_label': '16.01.99 Commercial and public services unallocated', 'value': 80.0},
        {'source_system': 'LEAP', 'scenario': 'Target', 'year': 2023, 'common_flow_code': '16.01', 'common_flow_label': '16.01 Commercial and public services', 'common_product_code': '17', 'common_product_label': '17 Electricity', '_configured_flow_group_label': '16.01 Commercial and public services', 'value': 110.0},
    ])
    spec = _make_spec('16.01', '16.01 Commercial and public services', configured_groups=[{'flow_boundary': '16.01.01', 'label': '16.01.01 Datacentres'}, {'flow_boundary': '16.01.99', 'label': '16.01.99 Commercial and public services unallocated'}])
    template = {'chart_generation': {'comparison_source_system': 'ESTO_EXTENDED', 'primary_area_source_system': 'LEAP', 'primary_area_scenario': 'Target', 'base_year': 2022}}
    series_labels = {'ESTO_EXTENDED|historical': 'ESTO Extended Historical', 'LEAP|Target': 'LEAP Target'}
    fig = renderer.build_area_chart(rows, spec, series_labels, template, group_col='_configured_flow_group_label')
    trace_names = [trace.name for trace in fig.data]
    assert '16.01 Commercial and public services' in trace_names
    assert '16.01.01 Datacentres' not in trace_names
    assert '16.01.99 Commercial and public services unallocated' not in trace_names

def test_transport_overview_trace_ordering_anchors_road_at_bottom() -> None:
    rows_placeholder = pd.DataFrame([
        {'source_system': 'ESTO', 'scenario': 'historical', 'year': 2022, 'common_flow_code': '15.01,15.03-15.06', 'common_flow_label': '15.01,15.03-15.06 Transport non-road', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 50.0},
        {'source_system': 'ESTO', 'scenario': 'historical', 'year': 2022, 'common_flow_code': '15.02', 'common_flow_label': '15.02 Road', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 200.0},
        {'source_system': 'LEAP', 'scenario': 'Target', 'year': 2023, 'common_flow_code': '15.01,15.03-15.06', 'common_flow_label': '15.01,15.03-15.06 Transport non-road', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 55.0},
        {'source_system': 'LEAP', 'scenario': 'Target', 'year': 2023, 'common_flow_code': '15.02', 'common_flow_label': '15.02 Road', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 210.0},
    ])
    rows_detailed = pd.DataFrame([
        {'source_system': 'ESTO', 'scenario': 'historical', 'year': 2022, 'common_flow_code': '15.01', 'common_flow_label': '15.01 Domestic air transport', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 20.0},
        {'source_system': 'ESTO', 'scenario': 'historical', 'year': 2022, 'common_flow_code': '15.02.01', 'common_flow_label': '15.02.01 Freight road', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 100.0},
        {'source_system': 'ESTO', 'scenario': 'historical', 'year': 2022, 'common_flow_code': '15.02.02', 'common_flow_label': '15.02.02 Passenger road', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 100.0},
        {'source_system': 'ESTO', 'scenario': 'historical', 'year': 2022, 'common_flow_code': '15.03', 'common_flow_label': '15.03 Rail', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 30.0},
        {'source_system': 'LEAP', 'scenario': 'Target', 'year': 2023, 'common_flow_code': '15.01', 'common_flow_label': '15.01 Domestic air transport', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 22.0},
        {'source_system': 'LEAP', 'scenario': 'Target', 'year': 2023, 'common_flow_code': '15.02.01', 'common_flow_label': '15.02.01 Freight road', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 105.0},
        {'source_system': 'LEAP', 'scenario': 'Target', 'year': 2023, 'common_flow_code': '15.02.02', 'common_flow_label': '15.02.02 Passenger road', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 105.0},
        {'source_system': 'LEAP', 'scenario': 'Target', 'year': 2023, 'common_flow_code': '15.03', 'common_flow_label': '15.03 Rail', 'common_product_code': '07', 'common_product_label': '07 Petroleum products', 'value': 33.0},
    ])
    spec = _make_spec('15', '15 Transport sector')
    template = {'chart_generation': {'comparison_source_system': 'ESTO', 'primary_area_source_system': 'LEAP', 'primary_area_scenario': 'Target', 'base_year': 2022}}
    series_labels = {'ESTO|historical': 'ESTO Historical', 'LEAP|Target': 'LEAP Target'}
    fig_placeholder = renderer.build_area_chart(rows_placeholder, spec, series_labels, template, group_col='common_flow_label')
    fig_detailed = renderer.build_area_chart(rows_detailed, spec, series_labels, template, group_col='common_flow_label')
    placeholder_traces = [t.name for t in fig_placeholder.data if 'total' not in t.name.lower()]
    detailed_traces = [t.name for t in fig_detailed.data if 'total' not in t.name.lower()]
    assert placeholder_traces[0] == '15.02 Road'
    assert placeholder_traces[1] == '15.01,15.03-15.06 Transport non-road'
    assert detailed_traces[0] == '15.02.01 Freight road'
    assert detailed_traces[1] == '15.02.02 Passenger road'
    assert detailed_traces[2] == '15.01 Domestic air transport'
    assert detailed_traces[3] == '15.03 Rail'
