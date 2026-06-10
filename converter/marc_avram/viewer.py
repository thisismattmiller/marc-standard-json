"""Generate a self-contained clientside diff viewer (``index.html``) at the
repository root, for HTTP hosting (e.g. GitHub Pages).

Data is ``fetch()``-ed at runtime from ``<versions dir>/<slug>/diffs.json``
plus the optional ``<versions dir>/updates.json``, so serve the tree over
HTTP (locally: ``python -m http.server``).
"""

from __future__ import annotations

from pathlib import Path

_CSS = r"""
:root{
  --bg:#fafbfc; --panel:#ffffff; --border:#e4e7eb; --border-soft:#eef0f3;
  --text:#1f2328; --muted:#6e7781; --faint:#9aa3ad; --accent:#0969da;
  --add-fg:#1a7f37; --add-line:#e9fbef; --add-chip:#dafbe1;
  --del-fg:#cf222e; --del-line:#fff0ef; --del-chip:#ffe3e0;
  --mod:#9a6700; --mod-chip:#fff1c2;
  --hunk-fg:#57606a; --hunk-bg:#f3f6f9;
  --shadow:0 1px 2px rgba(31,35,40,.04),0 1px 6px rgba(31,35,40,.05);
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--text);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
header{display:flex;align-items:center;gap:20px;padding:14px 24px;
  border-bottom:1px solid var(--border);background:var(--panel);position:sticky;top:0;z-index:10}
header h1{font-size:15px;margin:0;font-weight:650;letter-spacing:-.01em}
header h1 .v{color:var(--faint);font-weight:400;margin-left:6px}
.tabs{display:flex;gap:2px;margin-left:auto;flex-wrap:wrap;background:#f0f2f5;
  border-radius:8px;padding:3px}
.tab{padding:5px 14px;border-radius:6px;color:var(--muted);cursor:pointer;
  font-size:13px;transition:color .12s}
.tab:hover{color:var(--text)}
.tab.active{background:var(--panel);color:var(--text);font-weight:600;
  box-shadow:0 1px 3px rgba(31,35,40,.12)}
.layout{display:flex;height:calc(100vh - 58px)}
.sidebar{width:272px;min-width:272px;border-right:1px solid var(--border);
  overflow:auto;background:var(--panel)}
.sidebar .head{padding:14px 20px 8px;color:var(--faint);font-size:11px;
  text-transform:uppercase;letter-spacing:.08em;position:sticky;top:0;
  background:var(--panel)}
.vrow{display:flex;align-items:center;gap:8px;padding:8px 12px;margin:1px 8px;
  cursor:pointer;border-radius:8px}
.vrow:hover{background:#f3f5f8}
.vrow.active{background:#eaf2fc}
.vrow.active .lab{color:var(--accent)}
.vrow .lab{font-weight:600;font-size:13px}
.vrow .sub{color:var(--faint);font-size:11.5px;margin-top:1px}
.vrow .right{margin-left:auto;text-align:right;white-space:nowrap}
.delta{font-family:var(--mono);font-size:11px}
.delta .a{color:var(--add-fg)} .delta .d{color:var(--del-fg)} .delta .m{color:var(--mod)}
.count{color:var(--faint);font-size:11px}
.main{flex:1;overflow:auto;padding:0 0 80px}
.toolbar{display:flex;align-items:center;gap:14px;padding:16px 28px;position:sticky;top:0;
  background:linear-gradient(var(--bg) 85%,rgba(250,251,252,0));z-index:5}
.toolbar h2{font-size:17px;margin:0;font-weight:650;letter-spacing:-.01em}
.toolbar .meta{color:var(--muted);font-size:12.5px}
.toolbar .sp{margin-left:auto}
.search{background:var(--panel);border:1px solid var(--border);border-radius:8px;
  color:var(--text);padding:7px 12px;font-size:13px;width:240px;outline:none}
.search:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(9,105,218,.12)}
.search::placeholder{color:var(--faint)}
.btn{background:var(--panel);border:1px solid var(--border);color:var(--muted);
  padding:7px 12px;border-radius:8px;cursor:pointer;font-size:12.5px}
.btn:hover{color:var(--text);border-color:#c9d1d9}
.summary{padding:8px 28px;color:var(--muted);font-size:13px}
.quicklist{display:flex;flex-wrap:wrap;gap:6px;margin:0 28px 18px;padding:14px 16px;
  border:1px solid var(--border);border-radius:10px;background:var(--panel);
  box-shadow:var(--shadow)}
.qitem{display:inline-flex;align-items:center;gap:7px;padding:3px 11px;cursor:pointer;
  border:1px solid var(--border-soft);border-radius:999px;font-size:12px;color:var(--text)}
.qitem:hover{border-color:var(--accent)}
.qitem:hover .qtag{color:var(--accent)}
.qtag{font-family:var(--mono);font-weight:650}
.qstatus{color:var(--faint);font-size:11px}
.qdot{width:7px;height:7px;border-radius:50%;flex:none}
.qdot.added{background:var(--add-fg)}
.qdot.removed{background:var(--del-fg)}
.qdot.modified{background:var(--mod)}
.file{margin:0 28px 16px;border:1px solid var(--border);border-radius:10px;
  overflow:hidden;background:var(--panel);box-shadow:var(--shadow);
  scroll-margin-top:64px}
.file-head{display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;
  background:var(--panel)}
.file:not(.collapsed) .file-head{border-bottom:1px solid var(--border-soft)}
.file-head:hover .tag{color:var(--accent)}
.badge{font-size:10px;font-weight:650;text-transform:uppercase;letter-spacing:.06em;
  padding:2.5px 8px;border-radius:999px}
.badge.added{background:var(--add-chip);color:var(--add-fg)}
.badge.removed{background:var(--del-chip);color:var(--del-fg)}
.badge.modified{background:var(--mod-chip);color:var(--mod)}
.file-head .tag{font-family:var(--mono);font-weight:650;font-size:13px}
.file-head .name{color:var(--muted);font-weight:400;font-size:13px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-head .chev{margin-left:auto;color:var(--faint);font-size:10px;transition:transform .15s}
.file.collapsed .chev{transform:rotate(-90deg)}
.file.collapsed .diff{display:none}
.diff{font-family:var(--mono);font-size:12px;line-height:1.6;overflow-x:auto}
/* lines live in a max-content wrapper so their backgrounds span the full
   scrollable width, not just the visible container */
.lines{width:max-content;min-width:100%}
.line{display:flex;white-space:pre;padding:0 14px;min-height:19px}
.line .gut{width:18px;color:var(--faint);user-select:none;flex:none;text-align:center}
.line.add{background:var(--add-line)} .line.add .gut{color:var(--add-fg)}
.line.del{background:var(--del-line)} .line.del .gut{color:var(--del-fg)}
.line.hunk{background:var(--hunk-bg);color:var(--hunk-fg)}
.line.ctx{color:var(--muted)}
.line .txt{flex:1}
.empty{padding:80px 20px;text-align:center;color:var(--faint)}
.extlink{font-size:12.5px;white-space:nowrap}
.extlink:hover{text-decoration:underline}
"""

_JS = r"""
const DIFFS = {};
let UPDATES = {};       // optional: loc.gov change lists
let FORMATS = [];
let fmt = null;
let stepIdx = null;     // index into steps, or null for the base overview
let query = "";

const $ = (s,r=document)=>r.querySelector(s);
const el = (t,c,txt)=>{const e=document.createElement(t); if(c)e.className=c; if(txt!=null)e.textContent=txt; return e;};

function fmtData(){return DIFFS[fmt];}

// -- hash routing: #auth-41, #bib-base, ... ---------------------------------
const ALIAS = {authority:"auth", bibliographic:"bib", holdings:"hold",
               classification:"class", community:"comm"};

function currentHash(){
  const id = stepIdx===null ? "base" : fmtData().steps[stepIdx].to;
  return "#"+(ALIAS[fmt]||fmt)+"-"+id;
}

function applyHash(){
  const m = decodeURIComponent(location.hash||"").match(/^#([a-z]+)-(.+)$/);
  if(!m) return false;
  const slug = FORMATS.find(s=>s===m[1]||ALIAS[s]===m[1]);
  if(!slug) return false;
  const d = DIFFS[slug];
  let idx = null;
  if(m[2]!=="base"){
    idx = d.steps.findIndex(s=>String(s.to)===m[2]);
    if(idx<0) return false;
  }
  fmt = slug; stepIdx = idx;
  return true;
}

function navigate(f, idx){
  fmt = f; stepIdx = idx;
  history.replaceState(null, "", currentHash());
  render();
}

function renderTabs(){
  const tabs=$("#tabs"); tabs.innerHTML="";
  FORMATS.forEach(f=>{
    const t=el("div","tab"+(f===fmt?" active":""),DIFFS[f].name);
    t.onclick=()=>navigate(f, DIFFS[f].steps.length?DIFFS[f].steps.length-1:null);
    tabs.appendChild(t);
  });
}

function renderSidebar(){
  const d=fmtData(), sb=$("#sidebar"); sb.innerHTML="";
  const head=el("div","head"); head.textContent=d.versions.length+" versions · "+d.steps.length+" updates";
  sb.appendChild(head);
  d.versions.forEach((v,i)=>{
    const step = i>0 ? d.steps[i-1] : null;
    const row=el("div","vrow"+((step?stepIdx===i-1:stepIdx===null)?" active":""));
    const main=el("div");
    main.appendChild(el("div","lab",v.label));
    main.appendChild(el("div","sub",(v.modified||"")+" · "+v.fields+" fields"));
    row.appendChild(main);
    const right=el("div","right");
    if(step){
      const dl=el("div","delta");
      if(step.added)dl.appendChild(el("span","a","+"+step.added+" "));
      if(step.removed)dl.appendChild(el("span","d","−"+step.removed+" "));
      if(step.modified)dl.appendChild(el("span","m","~"+step.modified));
      if(!step.added&&!step.removed&&!step.modified)dl.appendChild(el("span","count","no field changes"));
      right.appendChild(dl);
    } else right.appendChild(el("div","count","initial"));
    row.appendChild(right);
    row.onclick=()=>navigate(fmt, step?i-1:null);
    sb.appendChild(row);
  });
}

function matches(file){
  if(!query)return true;
  const q=query.toLowerCase();
  if(file.tag.toLowerCase().includes(q))return true;
  return file.lines.some(l=>l[1].toLowerCase().includes(q));
}

function labelOf(file){
  for(const l of file.lines){const m=l[1].match(/"label"\s*:\s*"([^"]+)"/); if(m)return m[1];}
  return "";
}

function changeLink(versionId){
  const u=(UPDATES[fmt]||{})[versionId];
  if(!u)return null;
  const a=el("a","extlink","LC change list ↗");
  a.href=u.url; a.target="_blank"; a.rel="noopener";
  if(u.date)a.title=u.label+" ("+u.date+")";
  return a;
}

function jumpTo(tag){
  let box=document.getElementById("f-"+tag);
  if(!box && query){                       // hidden by the filter: clear it
    query=""; const s=$(".search"); if(s)s.value="";
    renderFiles(fmtData().steps[stepIdx]);
    box=document.getElementById("f-"+tag);
  }
  if(!box)return;
  box.classList.remove("collapsed");
  // instant, not smooth: a lingering smooth-scroll animation would fight the
  // scroll reset when the user switches updates mid-flight
  box.scrollIntoView({block:"start"});
}

function renderQuicklist(step){
  const list=el("div","quicklist");
  step.files.forEach(f=>{
    const a=el("a","qitem");
    a.appendChild(el("span","qdot "+f.status));
    a.appendChild(el("span","qtag",f.tag));
    a.appendChild(el("span","qstatus",f.status));
    a.onclick=()=>jumpTo(f.tag);
    list.appendChild(a);
  });
  return list;
}

function renderMain(){
  const d=fmtData(), main=$("#main"); main.innerHTML="";
  main.scrollTo({top:0,behavior:"instant"});   // cancels any in-flight smooth scroll
  const bar=el("div","toolbar");
  if(stepIdx===null){
    bar.appendChild(el("h2",null,d.versions[0]?d.versions[0].label:"—"));
    bar.appendChild(el("span","meta","initial version · "+(d.versions[0]?d.versions[0].fields:0)+" fields"));
    const bl=changeLink("base"); if(bl)bar.appendChild(bl);
    main.appendChild(bar);
    main.appendChild(el("div","summary","This is the earliest captured state. Select a later update on the left to see what changed."));
    return;
  }
  const step=d.steps[stepIdx];
  bar.appendChild(el("h2",null,step.toLabel));
  bar.appendChild(el("span","meta",(step.date||"")+"  ·  "+
     step.added+" added · "+step.removed+" removed · "+step.modified+" modified"));
  const cl=changeLink(step.to); if(cl)bar.appendChild(cl);
  const sp=el("div","sp"); bar.appendChild(sp);
  const search=el("input","search"); search.placeholder="Filter fields / text…"; search.value=query;
  search.oninput=()=>{query=search.value; renderFiles(step);};
  bar.appendChild(search);
  const ex=el("button","btn","Expand all"); ex.onclick=()=>toggleAll(false);
  const co=el("button","btn","Collapse all"); co.onclick=()=>toggleAll(true);
  bar.appendChild(ex); bar.appendChild(co);
  main.appendChild(bar);
  if(step.files.length) main.appendChild(renderQuicklist(step));
  const host=el("div"); host.id="files"; main.appendChild(host);
  renderFiles(step);
}

function renderFiles(step){
  const host=$("#files"); host.innerHTML="";
  const files=step.files.filter(matches);
  if(!files.length){host.appendChild(el("div","empty",
     step.files.length?"No fields match “"+query+"”":"No field-level changes in this update.")); return;}
  files.forEach(f=>{
    const big=f.lines.length>400;
    const box=el("div","file"+(big?" collapsed":""));
    box.id="f-"+f.tag;
    const head=el("div","file-head");
    head.appendChild(el("span","badge "+f.status,f.status));
    head.appendChild(el("span","tag",f.tag));
    head.appendChild(el("span","name",labelOf(f)));
    const chev=el("span","chev","▼"); head.appendChild(chev);
    head.onclick=()=>box.classList.toggle("collapsed");
    box.appendChild(head);
    const diff=el("div","diff");
    const lines=el("div","lines");
    f.lines.forEach(([m,t])=>{
      const cls=m==="+"?"add":m==="-"?"del":m==="@"?"hunk":"ctx";
      const line=el("div","line "+cls);
      line.appendChild(el("span","gut",m==="@"?"":m===" "?"":m));
      line.appendChild(el("span","txt",t));
      lines.appendChild(line);
    });
    diff.appendChild(lines);
    box.appendChild(diff);
    host.appendChild(box);
  });
}

function toggleAll(collapse){
  document.querySelectorAll(".file").forEach(b=>b.classList.toggle("collapsed",collapse));
}

function render(){
  if(!FORMATS.length){document.body.innerHTML="<div class='empty'>No diff data found.</div>";return;}
  renderTabs(); renderSidebar(); renderMain();
}

async function boot(){
  $("#main").appendChild(el("div","empty","Loading…"));
  const loaded = await Promise.all(SLUGS.map(async s=>{
    try{
      const r = await fetch(VERSIONS_DIR+"/"+s+"/diffs.json");
      return r.ok ? [s, await r.json()] : null;
    }catch(e){ return null; }
  }));
  for(const it of loaded) if(it) DIFFS[it[0]] = it[1];
  try{
    const r = await fetch(VERSIONS_DIR+"/updates.json");
    if(r.ok) UPDATES = await r.json();
  }catch(e){}
  FORMATS = Object.keys(DIFFS);
  if(!FORMATS.length){render();return;}
  if(!applyHash()){
    fmt = FORMATS[0];
    stepIdx = fmtData().steps.length ? fmtData().steps.length-1 : null;
    history.replaceState(null, "", currentHash());
  }
  render();
}
window.addEventListener("hashchange",()=>{ if(applyHash()) render(); });
boot();
"""


def write_viewer(root_dir: str | Path, slugs: list[str],
                 versions_dir: str = "versions") -> Path:
    """Write ``index.html`` into ``root_dir``; it fetches each format's
    ``diffs.json`` (and ``updates.json``) from ``versions_dir``, given
    relative to the page so it works on GitHub Pages project sites."""
    import json as _json
    root_dir = Path(root_dir)
    config = (f"const SLUGS = {_json.dumps(slugs)};\n"
              f"const VERSIONS_DIR = {_json.dumps(versions_dir)};\n")
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MARC 21 · Version Diff Viewer</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>MARC 21<span class="v">version diff</span></h1>
  <div class="tabs" id="tabs"></div>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar"></aside>
  <main class="main" id="main"></main>
</div>
<script>{config}{_JS}</script>
</body>
</html>
"""
    out = root_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
