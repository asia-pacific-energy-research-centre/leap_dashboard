#%%
"""Build the configurable, front-end-only Common ESTO dashboard tour."""

#%%
from __future__ import annotations

import json
from functools import lru_cache
from html import escape
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GUIDE_CONFIG_PATH = REPO_ROOT / "config" / "common_esto_dashboard" / "guide_config.json"


GUIDE_CSS = """
.dashboard-guide-launch {
  display:inline-flex;align-items:center;gap:5px;padding:5px 10px;
  border:1px solid #1f6feb;border-radius:999px;background:#fff;color:#0b3d5c;
  font:inherit;font-size:12px;font-weight:750;white-space:nowrap;cursor:pointer;
  box-shadow:0 1px 2px rgba(15,23,42,.08);
}
.dashboard-guide-launch:hover,.dashboard-guide-launch:focus-visible {
  background:#e8f0fe;outline:2px solid rgba(31,111,235,.28);outline-offset:2px;
}
.dashboard-guide-launch span { display:inline-grid;place-items:center;width:16px;height:16px;border:1px solid currentColor;border-radius:50%;font-size:10px; }
.dashboard-guide-backdrop { position:fixed;inset:0;z-index:1000;background:rgba(15,35,55,.66); }
.dashboard-guide-dialog {
  position:fixed;left:50%;top:50%;z-index:1010;width:min(680px,calc(100vw - 28px));
  max-height:calc(100vh - 28px);box-sizing:border-box;overflow:auto;
  transform:translate(-50%,-50%);padding:18px;border:1px solid #b8c9dc;
  border-radius:10px;background:#fff;color:#173452;box-shadow:0 22px 70px rgba(13,37,76,.42);
}
.dashboard-guide-dialog.guide-has-rich-content { width:min(1180px,calc(100vw - 28px)); }
.dashboard-guide-backdrop[hidden],.dashboard-guide-dialog[hidden] { display:none!important; }
.dashboard-guide-progress { color:#64748b;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase; }
.dashboard-guide-close { float:right;border:0;background:transparent;color:#64748b;font-size:24px;line-height:.8;cursor:pointer; }
.dashboard-guide-kicker { margin-top:15px;color:#e7672a;font-size:10px;font-weight:850;letter-spacing:.14em; }
.dashboard-guide-title { margin:5px 0 8px;font-size:23px;line-height:1.18; }
.dashboard-guide-copy { margin:0;color:#475569;font-size:15px;line-height:1.58; }
.dashboard-guide-image { display:block;width:100%;max-height:58vh;margin-top:14px;object-fit:contain;border:1px solid #cbd8e7;border-radius:6px;background:#f8fafc; }
.dashboard-guide-gallery { display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:10px;margin-top:14px; }
.dashboard-guide-gallery figure { min-width:0;margin:0; }
.dashboard-guide-gallery-images { display:grid;grid-template-columns:repeat(auto-fit,minmax(0,1fr));gap:10px; }
.dashboard-guide-gallery-images img { display:block;width:100%;max-height:56vh;object-fit:contain;border:1px solid #cbd8e7;border-radius:6px;background:#f8fafc; }
.dashboard-guide-gallery figcaption { margin-top:5px;color:#64748b;font-size:12px;font-weight:650;text-align:center; }
.dashboard-guide-gallery button { width:34px;height:34px;border:1px solid #93b5d8;border-radius:50%;background:#eef5fc;color:#0b3d5c;font-size:18px;cursor:pointer; }
.dashboard-guide-gallery button:disabled { opacity:.4;cursor:default; }
.dashboard-guide-table { margin-top:14px;overflow-x:auto;border:1px solid #cbd8e7;border-radius:6px; }
.dashboard-guide-table-caption { padding:8px 10px;background:#eef5fc;color:#0b3d5c;font-size:13px;font-weight:750; }
.dashboard-guide-table table { width:100%;min-width:640px;border-collapse:collapse;color:#334155;font-size:13px; }
.dashboard-guide-table th,.dashboard-guide-table td { padding:7px 9px;border-top:1px solid #dbe5ef;text-align:left;vertical-align:top; }
.dashboard-guide-table th { background:#f8fafc;color:#0b3d5c; }
.dashboard-guide-image[hidden],.dashboard-guide-gallery[hidden],.dashboard-guide-table[hidden] { display:none!important; }
.dashboard-guide-actions { display:flex;align-items:center;justify-content:space-between;margin-top:17px; }
.dashboard-guide-actions button { border:0;border-radius:6px;padding:9px 13px;background:transparent;color:#173452;font-weight:700;cursor:pointer; }
.dashboard-guide-next { background:#1f6feb!important;color:#fff!important; }
.dashboard-guide-highlight { position:relative!important;z-index:1005!important;box-shadow:0 0 0 4px #ff9868,0 0 0 8px rgba(255,255,255,.96)!important;border-radius:5px; }
.page-header.dashboard-guide-layer { z-index:1004; }
@media (max-width:640px) {
  .dashboard-guide-dialog { top:auto;bottom:10px;transform:translateX(-50%);max-height:72vh;padding:15px; }
  .dashboard-guide-title { font-size:20px; }
  .dashboard-guide-copy { font-size:14px; }
  .dashboard-guide-gallery { gap:5px; }
  .dashboard-guide-gallery button { width:29px;height:29px; }
}
"""


GUIDE_DIALOG_HTML = """
<div id="dashboard-guide-backdrop" class="dashboard-guide-backdrop" hidden></div>
<aside id="dashboard-guide-dialog" class="dashboard-guide-dialog" hidden role="dialog" aria-modal="true" aria-labelledby="dashboard-guide-title" aria-describedby="dashboard-guide-copy">
  <div class="dashboard-guide-progress"><span id="dashboard-guide-step">1</span> of <span id="dashboard-guide-total">1</span><button id="dashboard-guide-close" class="dashboard-guide-close" type="button" aria-label="Close guide">&times;</button></div>
  <div id="dashboard-guide-kicker" class="dashboard-guide-kicker"></div>
  <h2 id="dashboard-guide-title" class="dashboard-guide-title"></h2>
  <p id="dashboard-guide-copy" class="dashboard-guide-copy"></p>
  <img id="dashboard-guide-image" class="dashboard-guide-image" alt="" hidden>
  <div id="dashboard-guide-gallery" class="dashboard-guide-gallery" hidden aria-label="Guide screenshots">
    <button id="dashboard-guide-gallery-previous" type="button" aria-label="Previous screenshot">&larr;</button>
    <figure><div id="dashboard-guide-gallery-images" class="dashboard-guide-gallery-images"></div><figcaption id="dashboard-guide-gallery-caption"></figcaption></figure>
    <button id="dashboard-guide-gallery-next" type="button" aria-label="Next screenshot">&rarr;</button>
  </div>
  <div id="dashboard-guide-table" class="dashboard-guide-table" hidden></div>
  <div class="dashboard-guide-actions"><button id="dashboard-guide-back" type="button">Back</button><button id="dashboard-guide-next" class="dashboard-guide-next" type="button">Next <span aria-hidden="true">&rarr;</span></button></div>
</aside>
"""


def guide_launch_button_html() -> str:
    """Return the guide launch button shared by index and chart pages."""
    return (
        '<button id="dashboard-guide-launch" class="dashboard-guide-launch" type="button" '
        'aria-haspopup="dialog" aria-controls="dashboard-guide-dialog">'
        '<span aria-hidden="true">?</span> Guide</button>'
    )


def validate_guide_config(config: dict) -> None:
    """Fail early when editorial changes would produce a broken guide."""
    def validate_steps(steps: object, list_name: str, require_non_empty: bool = True) -> set[str]:
        if not isinstance(steps, list) or (require_non_empty and not steps):
            requirement = "a non-empty list" if require_non_empty else "a list"
            raise ValueError(f"Guide config requires {list_name} to be {requirement}.")
        seen: set[str] = set()
        for position, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise ValueError(f"{list_name} step {position} must be an object.")
            for key in ("id", "target", "title", "copy"):
                if not str(step.get(key, "")).strip():
                    raise ValueError(f"{list_name} step {position} is missing {key}.")
            step_id = str(step["id"])
            if step_id in seen:
                raise ValueError(f"Duplicate guide step id in {list_name}: {step_id}")
            seen.add(step_id)
            table = step.get("table")
            if table is not None:
                if not isinstance(table, dict):
                    raise ValueError(f"{list_name} step {position} table must be an object.")
                headers = table.get("headers")
                rows = table.get("rows")
                if not isinstance(headers, list) or not headers:
                    raise ValueError(f"{list_name} step {position} table requires headers.")
                if not isinstance(rows, list) or any(
                    not isinstance(row, list) or len(row) != len(headers) for row in rows
                ):
                    raise ValueError(
                        f"{list_name} step {position} table rows must match the header count."
                    )
        return seen

    step_ids_by_list: dict[str, set[str]] = {}
    for list_name in ("chart_steps", "index_steps", "diagnostics_steps", "tree_steps"):
        step_ids_by_list[list_name] = validate_steps(config.get(list_name), list_name)
    purposes = config.get("page_purposes")
    if not isinstance(purposes, dict) or not str(purposes.get("default", "")).strip():
        raise ValueError("Guide config requires page_purposes.default.")
    page_steps = config.get("page_steps", {})
    if not isinstance(page_steps, dict):
        raise ValueError("Guide config page_steps must be an object when provided.")
    for page_key, steps in page_steps.items():
        page_ids = validate_steps(steps, f"page_steps.{page_key}", require_non_empty=False)
        collisions = page_ids & step_ids_by_list["chart_steps"]
        if collisions:
            duplicate = sorted(collisions)[0]
            raise ValueError(f"Page-specific guide step id duplicates a chart step: {duplicate}")


@lru_cache(maxsize=4)
def load_guide_config(config_path: str = str(DEFAULT_GUIDE_CONFIG_PATH)) -> dict:
    """Load and validate the editable guide content."""
    path = Path(config_path)
    config = json.loads(path.read_text(encoding="utf-8"))
    validate_guide_config(config)
    return config


def _resolved_steps(config: dict, page_kind: str, page_key: str, page_label: str) -> list[dict]:
    list_by_kind = {
        "chart": "chart_steps",
        "index": "index_steps",
        "diagnostics": "diagnostics_steps",
        "tree": "tree_steps",
    }
    source_steps = list(config[list_by_kind[page_kind]])
    if page_kind == "chart":
        page_specific_steps = list(config.get("page_steps", {}).get(page_key, []))
        insert_at = next(
            (index + 1 for index, step in enumerate(source_steps) if step.get("id") == "chart-card"),
            len(source_steps),
        )
        source_steps[insert_at:insert_at] = page_specific_steps
    purposes = config["page_purposes"]
    page_purpose = str(purposes.get(page_key, purposes["default"]))
    replacements = {"page_key": page_key, "page_label": page_label, "page_purpose": page_purpose}
    resolved: list[dict] = []
    for source in source_steps:
        step = dict(source)
        for field in ("title", "copy"):
            step[field] = str(step[field]).format(**replacements)
        resolved.append(step)
    return resolved


def _guide_js(steps: list[dict], guide_label: str) -> str:
    steps_json = json.dumps(steps, ensure_ascii=False).replace("</", "<\\/")
    label_json = json.dumps(guide_label, ensure_ascii=False)
    return f"""
(function() {{
  var steps = {steps_json};
  var guideLabel = {label_json};
  var get = function(selector) {{ return document.querySelector(selector); }};
  var launch = get('#dashboard-guide-launch');
  var dialog = get('#dashboard-guide-dialog');
  var backdrop = get('#dashboard-guide-backdrop');
  if (!launch || !dialog || !backdrop || launch.dataset.guideBound === '1') return;

  var current = 0;
  var direction = 1;
  var launchFocus = null;
  var galleryItems = [];
  var galleryIndex = 0;
  var title = get('#dashboard-guide-title');
  var copy = get('#dashboard-guide-copy');
  var image = get('#dashboard-guide-image');
  var gallery = get('#dashboard-guide-gallery');
  var galleryImages = get('#dashboard-guide-gallery-images');
  var galleryCaption = get('#dashboard-guide-gallery-caption');
  var galleryPrevious = get('#dashboard-guide-gallery-previous');
  var galleryNext = get('#dashboard-guide-gallery-next');
  var tableContainer = get('#dashboard-guide-table');
  var back = get('#dashboard-guide-back');
  var next = get('#dashboard-guide-next');
  var closeButton = get('#dashboard-guide-close');

  var clearHighlight = function() {{
    document.querySelectorAll('.dashboard-guide-highlight').forEach(function(node) {{ node.classList.remove('dashboard-guide-highlight'); }});
    document.querySelectorAll('.dashboard-guide-layer').forEach(function(node) {{ node.classList.remove('dashboard-guide-layer'); }});
  }};
  var resolveTarget = function(step) {{
    return step.target.split(',').map(function(selector) {{ return get(selector.trim()); }}).find(Boolean) || null;
  }};
  steps = steps.filter(function(step) {{ return resolveTarget(step) || !step.optional; }});
  var findAvailableIndex = function(index, stepDirection) {{
    var candidate = Math.max(0, Math.min(index, steps.length - 1));
    while (candidate >= 0 && candidate < steps.length) {{
      if (resolveTarget(steps[candidate]) || !steps[candidate].optional) return candidate;
      candidate += stepDirection;
    }}
    return Math.max(0, Math.min(index, steps.length - 1));
  }};
  var renderGallery = function() {{
    var item = galleryItems[galleryIndex];
    galleryImages.replaceChildren();
    if (!item) return;
    (item.images || [item]).forEach(function(imageItem) {{
      var node = document.createElement('img');
      node.src = imageItem.image || '';
      node.alt = imageItem.alt || '';
      galleryImages.appendChild(node);
    }});
    var count = String(galleryIndex + 1) + ' of ' + String(galleryItems.length);
    galleryCaption.textContent = item.caption ? count + ' — ' + item.caption : count;
    galleryPrevious.disabled = galleryItems.length < 2;
    galleryNext.disabled = galleryItems.length < 2;
  }};
  var renderTable = function(table) {{
    tableContainer.replaceChildren();
    tableContainer.hidden = !table;
    if (!table) return;
    var caption = document.createElement('div');
    caption.className = 'dashboard-guide-table-caption';
    caption.textContent = table.caption || '';
    var htmlTable = document.createElement('table');
    var head = document.createElement('thead');
    var headRow = document.createElement('tr');
    (table.headers || []).forEach(function(value) {{ var cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = value; headRow.appendChild(cell); }});
    head.appendChild(headRow);
    var body = document.createElement('tbody');
    (table.rows || []).forEach(function(row) {{ var tableRow = document.createElement('tr'); row.forEach(function(value) {{ var cell = document.createElement('td'); cell.textContent = value; tableRow.appendChild(cell); }}); body.appendChild(tableRow); }});
    htmlTable.append(head, body);
    tableContainer.append(caption, htmlTable);
  }};
  var show = function(index, stepDirection) {{
    direction = stepDirection || direction;
    current = findAvailableIndex(index, direction);
    var step = steps[current];
    var target = resolveTarget(step);
    clearHighlight();
    get('#dashboard-guide-kicker').textContent = guideLabel;
    get('#dashboard-guide-step').textContent = String(current + 1);
    get('#dashboard-guide-total').textContent = String(steps.length);
    title.textContent = step.title;
    copy.textContent = step.copy;
    image.hidden = !step.image;
    if (step.image) {{ image.src = step.image; image.alt = step.image_alt || step.title; }} else {{ image.removeAttribute('src'); image.alt = ''; }}
    galleryItems = step.gallery || [];
    galleryIndex = 0;
    gallery.hidden = !galleryItems.length;
    if (galleryItems.length) renderGallery(); else {{ galleryImages.replaceChildren(); galleryCaption.textContent = ''; }}
    renderTable(step.table);
    dialog.classList.toggle('guide-has-rich-content', Boolean(step.image || galleryItems.length || step.table));
    back.style.visibility = current === 0 ? 'hidden' : 'visible';
    next.innerHTML = current === steps.length - 1 ? 'Done <span aria-hidden="true">✓</span>' : 'Next <span aria-hidden="true">→</span>';
    if (target) {{
      target.classList.add('dashboard-guide-highlight');
      var pageHeader = target.closest('.page-header');
      if (pageHeader) pageHeader.classList.add('dashboard-guide-layer');
      target.scrollIntoView({{behavior:'smooth',block:'center',inline:'nearest'}});
    }}
  }};
  var close = function() {{
    dialog.hidden = true;
    backdrop.hidden = true;
    clearHighlight();
    if (launchFocus && launchFocus.focus) launchFocus.focus();
  }};
  var move = function(stepDirection) {{
    if (stepDirection > 0 && current === steps.length - 1) {{ close(); return; }}
    show(current + stepDirection, stepDirection);
  }};

  launch.dataset.guideBound = '1';
  launch.addEventListener('click', function() {{
    launchFocus = document.activeElement;
    var pageHeader = get('#page-header');
    if (pageHeader) {{
      pageHeader.classList.remove('is-collapsed');
      var headerToggle = get('#header-toggle');
      if (headerToggle) {{
        headerToggle.textContent = '▴';
        headerToggle.setAttribute('aria-expanded', 'true');
        headerToggle.setAttribute('aria-label', 'Collapse header');
      }}
    }}
    dialog.hidden = false;
    backdrop.hidden = false;
    show(0, 1);
    closeButton.focus();
  }});
  closeButton.addEventListener('click', close);
  backdrop.addEventListener('click', close);
  back.addEventListener('click', function() {{ move(-1); }});
  next.addEventListener('click', function() {{ move(1); }});
  galleryPrevious.addEventListener('click', function() {{ galleryIndex = (galleryIndex - 1 + galleryItems.length) % galleryItems.length; renderGallery(); }});
  galleryNext.addEventListener('click', function() {{ galleryIndex = (galleryIndex + 1) % galleryItems.length; renderGallery(); }});
  document.addEventListener('keydown', function(event) {{
    if (dialog.hidden) return;
    if (event.key === 'Escape') close();
    if (event.key === 'ArrowLeft' && event.target.tagName !== 'BUTTON') move(-1);
    if (event.key === 'ArrowRight' && event.target.tagName !== 'BUTTON') move(1);
    if (event.key === 'Tab') {{
      var focusable = Array.from(dialog.querySelectorAll('button:not([disabled]),a[href]')).filter(function(node) {{ return node.offsetParent !== null; }});
      if (!focusable.length) return;
      var first = focusable[0]; var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {{ event.preventDefault(); last.focus(); }}
      else if (!event.shiftKey && document.activeElement === last) {{ event.preventDefault(); first.focus(); }}
    }}
  }});
}})();
"""


def build_guide_fragments(page_kind: str, page_key: str, page_label: str) -> dict[str, str]:
    """Return the CSS, dialog HTML and script for one generated page."""
    if page_kind not in {"chart", "index", "diagnostics", "tree"}:
        raise ValueError(f"Unsupported guide page kind: {page_kind}")
    config = load_guide_config()
    steps = _resolved_steps(config, page_kind, page_key, page_label)
    return {
        "css": GUIDE_CSS,
        "dialog_html": GUIDE_DIALOG_HTML,
        "script": _guide_js(steps, str(config.get("guide_label", "DASHBOARD GUIDE"))),
        "launch_button_html": guide_launch_button_html(),
    }


#%%
