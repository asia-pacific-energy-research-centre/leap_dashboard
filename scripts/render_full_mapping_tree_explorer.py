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


def render_full_tree_explorer() -> Path:
    trees = pd.read_csv(MAPPINGS_ROOT / "results" / "tree_structure" / "all_dataset_trees.csv", low_memory=False)
    routes = pd.read_csv(
        MAPPINGS_ROOT / "results" / "common_esto" / "structural_artifacts" / "source_pair_to_common_row.csv",
        usecols=["source_system", "original_source_flow", "original_source_product", "component_esto_flow", "component_esto_product", "common_flow_label", "common_row_id", "relationship_id", "comparison_scope"],
        low_memory=False,
    ).drop_duplicates()
    tree_json = json.dumps(trees.fillna("").to_dict("records"), ensure_ascii=False).replace("</", "<\\/")
    route_json = json.dumps(routes.fillna("").to_dict("records"), ensure_ascii=False).replace("</", "<\\/")
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Full mapping tree explorer</title><style>
body{{font:14px system-ui,sans-serif;margin:0;background:#f3f6fa;color:#16202a}}main{{max-width:1600px;margin:auto;padding:20px}}.box{{background:#fff;border:1px solid #d5dee8;border-radius:8px;padding:12px;margin:10px 0}}select,input{{padding:7px;margin-right:8px}}.trees{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.tree{{max-height:70vh;overflow:auto}}details{{margin-left:12px}}summary{{cursor:pointer;padding:3px 0}}button{{border:0;background:transparent;text-align:left;padding:3px;cursor:pointer;font:inherit}}button:hover,button.selected{{background:#dcebfa;border-radius:4px}}button.mapped{{font-weight:600}}button.target{{background:#fff3cd}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #d5dee8;padding:5px;text-align:left;vertical-align:top}}.muted{{color:#59687a}}@media(max-width:900px){{.trees{{grid-template-columns:1fr}}.tree{{max-height:45vh}}}}</style><main>
<h1>Full mapping tree explorer</h1><p>Every source hierarchy node is available. Source parent/child edges, mapping routes, and real ESTO target edges are shown independently.</p>
<div class="box"><label>Source tree <select id="choose"></select></label><label>Find node <input id="find" placeholder="code or label"></label><span id="count" class="muted"></span></div>
<div class="trees"><section class="box tree"><h2 id="left-title"></h2><div id="left"></div></section><section class="box tree"><h2>ESTO component hierarchy <small>(real target edges)</small></h2><p class="muted">This is the original ESTO hierarchy used to decide whether target rows are genuine parent/child relationships.</p><div id="right"></div></section><section class="box tree"><h2>Common ESTO flow hierarchy</h2><p class="muted">This is the Common ESTO comparison representation. Highlighting follows mapped Common ESTO flow labels.</p><div id="common"></div></section></div>
<section class="box"><h2 id="detail-title">Mapping routes</h2><p id="note" class="muted">Select a node. The table counts each Common ESTO row ID once, even when routes repeat it.</p><div id="detail"></div></section>
<script>const T={tree_json},R={route_json},L=document.querySelector('#left'),Z=document.querySelector('#right'),C=document.querySelector('#common'),S=document.querySelector('#choose'),Q=document.querySelector('#find'),sys={{leap:'LEAP',ninth:'NINTH',esto:'ESTO'}};let active=[];
const k=n=>n.dataset+'|'+n.axis, name=n=>n.label||n.code;
function draw(nodes,el,marks,source){{el.innerHTML='';let by={{}};nodes.forEach(n=>(by[n.parent_code||'ROOT']??=[]).push(n));function add(p,to){{(by[p]||[]).sort((a,b)=>name(a).localeCompare(name(b))).forEach(n=>{{let kids=by[n.code]||[],w=document.createElement(kids.length?'details':'div'),line=document.createElement(kids.length?'summary':'span'),b=document.createElement('button');b.textContent=name(n);b.title=n.code;if(marks.has(n.code))b.classList.add(source?'mapped':'target');if(source)b.onclick=()=>selectNode(n);line.append(b);w.append(line);if(kids.length){{w.open=n.level<2;add(n.code,w)}}to.append(w)}})}}add('ROOT',el)}}
function switchTree(){{let [d,a]=S.value.split('|');active=T.filter(n=>n.dataset===d&&n.axis===a);document.querySelector('#left-title').textContent=`Full ${{d.toUpperCase()}} ${{a}} tree (${{active.length}} nodes)`;document.querySelector('#count').textContent=`${{active.length}} source nodes`;draw(active,L,new Set(),true);draw(T.filter(n=>n.dataset==='esto'&&n.axis==='flow'),Z,new Set(),false);draw(T.filter(n=>n.dataset==='common_esto'&&n.axis==='flow'),C,new Set(),false);document.querySelector('#detail').innerHTML='';document.querySelector('#detail-title').textContent='Mapping routes'}}
function selectNode(n){{let [d,a]=S.value.split('|'),found=R.filter(r=>r.source_system===sys[d]&&((a==='flow'||a==='sector')?r.original_source_flow===n.code:r.original_source_product===n.code)),ids=[...new Set(found.map(r=>r.common_row_id).filter(Boolean))],flows=new Set(found.map(r=>r.component_esto_flow)),commonFlows=new Set(found.map(r=>r.common_flow_label));draw(active,L,new Set([n.code]),true);draw(T.filter(x=>x.dataset==='esto'&&x.axis==='flow'),Z,flows,false);draw(T.filter(x=>x.dataset==='common_esto'&&x.axis==='flow'),C,commonFlows,false);document.querySelector('#detail-title').textContent=name(n)+' — mapping routes';document.querySelector('#note').textContent=`${{found.length}} routes; ${{ids.length}} unique Common ESTO row IDs. The middle panel is real ESTO hierarchy; the right panel is the Common ESTO comparison hierarchy.`;let rows=found.slice(0,500).map(r=>`<tr><td>${{r.original_source_flow}}</td><td>${{r.original_source_product}}</td><td>${{r.component_esto_flow}} / ${{r.component_esto_product}}</td><td>${{r.common_row_id}}</td><td>${{r.comparison_scope}}</td></tr>`).join('');document.querySelector('#detail').innerHTML=rows?`<table><thead><tr><th>Source flow</th><th>Source product</th><th>ESTO component</th><th>Common row ID</th><th>Scope</th></tr></thead><tbody>${{rows}}</tbody></table>${{found.length>500?'<p class="muted">First 500 routes shown.</p>':''}}`:'<p class="muted">No registered structural route for this node.</p>'}}
S.onchange=switchTree;Q.oninput=()=>{{let q=Q.value.toLowerCase();L.querySelectorAll('button').forEach(b=>b.parentElement.style.display=(!q||b.textContent.toLowerCase().includes(q)||b.title.toLowerCase().includes(q))?'':'none')}};[...new Set(T.filter(n=>n.dataset!=='common_esto').map(k))].forEach(x=>S.add(new Option(x.replace('|',' / '),x)));S.value='leap|sector';switchTree();</script></main></html>'''
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    return OUTPUT_PATH


#%%
if __name__ == "__main__":
    print(render_full_tree_explorer())

#%%
