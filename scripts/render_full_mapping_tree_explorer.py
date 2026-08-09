#%%
"""Render the full all-node mapping tree explorer from structural artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


#%%
REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPINGS_ROOT = REPO_ROOT.parent / "leap_mappings"
OUTPUT_PATH = REPO_ROOT / "outputs" / "prototypes" / "mapping_tree_explorer_prototype.html"
DISPLAY_YEARS = [2022, 2030, 2040, 2060]

try:  # pragma: no cover - direct-script import shim
    from codebase.common_esto_dashboard_guide import build_guide_fragments
except ModuleNotFoundError:  # pragma: no cover - direct-script import shim
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from codebase.common_esto_dashboard_guide import build_guide_fragments


def render_full_tree_explorer(
    output_path: Path = OUTPUT_PATH,
    comparison_data: pd.DataFrame | None = None,
    prefer_extended_esto: bool = False,
) -> Path:
    trees = pd.read_csv(MAPPINGS_ROOT / "results" / "tree_structure" / "all_dataset_trees.csv", low_memory=False)
    routes = pd.read_csv(
        MAPPINGS_ROOT / "results" / "common_esto" / "structural_artifacts" / "source_pair_to_common_row.csv",
        usecols=["source_system", "original_source_flow", "original_source_product", "component_esto_flow", "component_esto_product", "common_flow_label", "common_row_id", "relationship_id", "comparison_scope"],
        low_memory=False,
    ).drop_duplicates()
    if comparison_data is not None:
        numeric = comparison_data.copy()
        numeric["value"] = pd.to_numeric(numeric["value"], errors="coerce").fillna(0.0)
        numeric["structural_scope"] = numeric["comparison_scope"].replace({
            "esto_leap": "leap_vs_esto",
            "esto_leap_ninth": "leap_vs_esto_vs_ninth",
            "esto_only": "esto_only",
            "leap_vs_ninth": "leap_vs_ninth",
        })
        totals = numeric.groupby(
            ["source_system", "structural_scope", "common_row_id"], dropna=False
        )["value"].sum().reset_index(name="dataset_total")
        routes = routes.merge(
            totals,
            left_on=["source_system", "comparison_scope", "common_row_id"],
            right_on=["source_system", "structural_scope", "common_row_id"],
            how="left",
        ).drop(columns="structural_scope")
        numeric_records = numeric.groupby(
            ["source_system", "structural_scope", "common_row_id", "scenario", "year"], dropna=False
        )["value"].sum().reset_index().to_dict("records")
    else:
        routes["dataset_total"] = pd.NA
        numeric_records = []
    extended_available = bool(
        comparison_data is not None
        and comparison_data["source_system"].astype(str).eq("ESTO_EXTENDED").any()
    )
    if extended_available:
        extended_tree = trees[trees["dataset"].eq("esto")].copy()
        extended_tree["dataset"] = "esto_extended"
        trees = pd.concat([trees, extended_tree], ignore_index=True)
    preferred_tree = "esto_extended|flow" if extended_available and prefer_extended_esto else "leap|sector"
    tree_json = json.dumps(trees.fillna("").to_dict("records"), ensure_ascii=False).replace("</", "<\\/")
    route_json = json.dumps(routes.fillna("").to_dict("records"), ensure_ascii=False).replace("</", "<\\/")
    numeric_json = json.dumps(numeric_records, ensure_ascii=False).replace("</", "<\\/")
    dashboard_guide = build_guide_fragments("tree", "mapping_tree_explorer", "Full mapping tree explorer")
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Full mapping tree explorer</title><style>
body{{font:14px system-ui,sans-serif;margin:0;background:#f3f6fa;color:#16202a}}main{{max-width:1600px;margin:auto;padding:20px}}.box{{background:#fff;border:1px solid #d5dee8;border-radius:8px;padding:12px;margin:10px 0}}select,input{{padding:7px;margin-right:8px}}.trees{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.tree{{max-height:70vh;overflow:auto}}details{{margin-left:12px}}summary{{cursor:pointer;padding:3px 0}}button{{border:0;background:transparent;text-align:left;padding:3px;cursor:pointer;font:inherit}}button:hover,button.selected{{background:#dcebfa;border-radius:4px}}button.mapped{{font-weight:600}}button.target{{background:#fff3cd}}small.map{{color:#59687a;font-size:11px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #d5dee8;padding:5px;text-align:left;vertical-align:top}}.muted{{color:#59687a}}@media(max-width:900px){{.trees{{grid-template-columns:1fr}}.tree{{max-height:45vh}}}}
{dashboard_guide["css"]}</style><main>
{dashboard_guide["launch_button_html"]}<h1>Full mapping tree explorer</h1><p>Every source hierarchy node is available. Source parent/child edges, mapping routes, and real ESTO target edges are shown independently.</p>
<div class="box"><label>Source tree <select id="choose"></select></label>{'<label><input id="use-extended" type="checkbox" checked> Use ESTO Extended instead of ESTO</label>' if extended_available and prefer_extended_esto else '<label><input id="use-extended" type="checkbox"> Use ESTO Extended instead of ESTO</label>' if extended_available else ''}<label>Mapping labels <select id="mapping-labels"><option value="off">Off</option><option value="esto">Original ESTO components</option><option value="common">Common ESTO targets</option></select></label><label>Year <select id="year"></select></label><label>Scenario <select id="scenario"></select></label><label>Magnitude <select id="magnitude"><option value="1">PJ</option><option value="1000">Thousands of PJ</option><option value="1000000">Millions of PJ</option></select></label><label>Find node <input id="find" placeholder="code or label"></label><span id="count" class="muted"></span></div>
<div class="trees"><section class="box tree"><h2 id="left-title"></h2><div id="left"></div></section><section class="box tree"><h2>ESTO component hierarchy <small>(real target edges)</small></h2><p class="muted">This is the original ESTO hierarchy used to decide whether target rows are genuine parent/child relationships.</p><div id="right"></div></section><section class="box tree"><h2>Common ESTO flow hierarchy</h2><p class="muted">This is the Common ESTO comparison representation. Highlighting follows mapped Common ESTO flow labels.</p><div id="common"></div></section></div>
<section class="box"><h2 id="detail-title">Mapping routes</h2><p id="note" class="muted">Select a node. The table counts each Common ESTO row ID once, even when routes repeat it.</p><div id="detail"></div></section>
<script>const T={tree_json},R={route_json},N={numeric_json},L=document.querySelector('#left'),Z=document.querySelector('#right'),C=document.querySelector('#common'),S=document.querySelector('#choose'),E=document.querySelector('#use-extended'),M=document.querySelector('#mapping-labels'),Y=document.querySelector('#year'),V=document.querySelector('#scenario'),G=document.querySelector('#magnitude'),Q=document.querySelector('#find'),sys={{leap:'LEAP',ninth:'NINTH',esto:'ESTO',esto_extended:'ESTO_EXTENDED'}};let active=[],lastNode=null,labels={{}};
const k=n=>n.dataset+'|'+n.axis, name=n=>n.label||n.code;
function draw(nodes,el,marks,source){{el.innerHTML='';let by={{}};nodes.forEach(n=>(by[n.parent_code||'ROOT']??=[]).push(n));function add(p,to){{(by[p]||[]).sort((a,b)=>name(a).localeCompare(name(b))).forEach(n=>{{let kids=by[n.code]||[],w=document.createElement(kids.length?'details':'div'),line=document.createElement(kids.length?'summary':'span'),b=document.createElement('button');b.textContent=name(n);b.title=n.code;if(marks.has(n.code))b.classList.add(source?'mapped':'target');if(source)b.onclick=()=>selectNode(n);line.append(b);if(source&&labels[n.code]){{let e=document.createElement('small');e.className='map';e.textContent=' → '+labels[n.code];line.append(e)}}w.append(line);if(kids.length){{w.open=n.level<2;add(n.code,w)}}to.append(w)}})}}add('ROOT',el)}}
function switchTree(){{let [d,a]=S.value.split('|');active=T.filter(n=>n.dataset===d&&n.axis===a);labels={{}};if(M.value!=='off'){{R.filter(r=>r.source_system===sys[d]).forEach(r=>{{let key=(a==='flow'||a==='sector')?r.original_source_flow:r.original_source_product,val=M.value==='esto'?r.component_esto_flow:r.common_flow_label;if(!key||!val)return;(labels[key]??=new Set()).add(val)}});Object.keys(labels).forEach(k=>{{let x=[...labels[k]];labels[k]=x.slice(0,2).join(', ')+(x.length>2?' +'+(x.length-2):'')}})}}document.querySelector('#left-title').textContent=`Full ${{d.toUpperCase()}} ${{a}} tree (${{active.length}} nodes)`;document.querySelector('#count').textContent=`${{active.length}} source nodes`;draw(active,L,new Set(),true);draw(T.filter(n=>n.dataset==='esto'&&n.axis==='flow'),Z,new Set(),false);draw(T.filter(n=>n.dataset==='common_esto'&&n.axis==='flow'),C,new Set(),false);document.querySelector('#detail').innerHTML='';document.querySelector('#detail-title').textContent='Mapping routes'}}
function selectNode(n){{lastNode=n;let [d,a]=S.value.split('|'),found=R.filter(r=>r.source_system===sys[d]&&((a==='flow'||a==='sector')?r.original_source_flow===n.code:r.original_source_product===n.code)),ids=[...new Set(found.map(r=>r.common_row_id).filter(Boolean))],flows=new Set(found.map(r=>r.component_esto_flow)),commonFlows=new Set(found.map(r=>r.common_flow_label)),unique=new Map(),divisor=Number(G.value),unit=G.options[G.selectedIndex].text;found.forEach(r=>{{let values=N.filter(x=>x.source_system===r.source_system&&x.structural_scope===r.comparison_scope&&x.common_row_id===r.common_row_id&&String(x.year)===Y.value&&(V.value==='all'||x.scenario===V.value)).map(x=>Number(x.value)),parts={{positive:values.filter(x=>x>0).reduce((s,x)=>s+x,0),negative:values.filter(x=>x<0).reduce((s,x)=>s+x,0)}};parts.net=parts.positive+parts.negative;if(r.common_row_id&&!unique.has(r.common_row_id))unique.set(r.common_row_id,parts);r.selected=parts}});let summary=[...unique.values()].reduce((s,x)=>({{positive:s.positive+x.positive,negative:s.negative+x.negative,net:s.net+x.net}}),{{positive:0,negative:0,net:0}}),format=v=>(v/divisor).toLocaleString(undefined,{{maximumFractionDigits:4}});draw(active,L,new Set([n.code]),true);draw(T.filter(x=>x.dataset==='esto'&&x.axis==='flow'),Z,flows,false);draw(T.filter(x=>x.dataset==='common_esto'&&x.axis==='flow'),C,commonFlows,false);document.querySelector('#detail-title').textContent=name(n)+' — mapping routes';document.querySelector('#note').textContent=`${{found.length}} routes; ${{ids.length}} unique Common ESTO row IDs; positive output ${{format(summary.positive)}}; negative input ${{format(summary.negative)}}; net ${{format(summary.net)}} ${{unit}}. Totals sum all economies for the selected year/scenario.`;let rows=found.slice(0,500).map(r=>`<tr><td>${{r.original_source_flow}}</td><td>${{r.original_source_product}}</td><td>${{r.component_esto_flow}} / ${{r.component_esto_product}}</td><td>${{r.common_row_id}}</td><td>${{format(r.selected.positive)}}</td><td>${{format(r.selected.negative)}}</td><td>${{format(r.selected.net)}}</td><td>${{r.comparison_scope}}</td></tr>`).join('');document.querySelector('#detail').innerHTML=rows?`<table><thead><tr><th>Source flow</th><th>Source product</th><th>ESTO component</th><th>Common row ID</th><th>Positive output (${{unit}})</th><th>Negative input (${{unit}})</th><th>Net (${{unit}})</th><th>Scope</th></tr></thead><tbody>${{rows}}</tbody></table>${{found.length>500?'<p class="muted">First 500 routes shown.</p>':''}}`:'<p class="muted">No registered structural route for this node.</p>'}}
S.onchange=switchTree;E&& (E.onchange=()=>{{let [d,a]=S.value.split('|');if(d==='esto'||d==='esto_extended')S.value=(E.checked?'esto_extended':'esto')+'|'+a;switchTree()}});M.onchange=switchTree;Y.onchange=()=>{{if(lastNode)selectNode(lastNode)}};V.onchange=()=>{{if(lastNode)selectNode(lastNode)}};G.onchange=()=>{{if(lastNode)selectNode(lastNode)}};Q.oninput=()=>{{let q=Q.value.toLowerCase();L.querySelectorAll('button').forEach(b=>b.parentElement.style.display=(!q||b.textContent.toLowerCase().includes(q)||b.title.toLowerCase().includes(q))?'':'none')}};[...new Set(T.filter(n=>n.dataset!=='common_esto').map(k))].forEach(x=>S.add(new Option(x.replace('|',' / '),x)));[{', '.join(str(year) for year in DISPLAY_YEARS)}].forEach(x=>Y.add(new Option(x,x)));V.add(new Option('All scenarios','all'));[...new Set(N.map(x=>x.scenario))].sort().forEach(x=>V.add(new Option(x,x)));S.value='{preferred_tree}';switchTree();</script>{dashboard_guide["dialog_html"]}<script>{dashboard_guide["script"]}</script></main></html>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


#%%
if __name__ == "__main__":
    print(render_full_tree_explorer())

#%%
