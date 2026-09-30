#!/usr/bin/env python3
"""Web interface for the invoice extractor."""
import os, tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse

from extract import extract, validate

MAX_BYTES = 10 * 1024 * 1024

app = FastAPI(title="Invoice Extractor")


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.post("/api/extract")
async def api_extract(file: UploadFile = File(...)):
    raw = await file.read()

    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "File too large (10 MB max)")
    if not raw.startswith(b"%PDF"):
        raise HTTPException(400, "Not a PDF")

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw)
            path = tmp.name

        invoice = extract(path)
        problems, checks = validate(invoice)

        if not checks:
            status = "unverified"
        elif problems:
            status = "flagged"
        else:
            status = "passed"

        return {
            "status": status,
            "checks_run": checks,
            "problems": problems,
            "invoice": invoice.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Extraction failed: {e}")
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invoice Extractor</title>
<style>
  :root { --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#e2e2e2;
          --ok:#0a7d36; --warn:#b45309; --bad:#b91c1c; --accent:#1d4ed8; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#111; --fg:#eee; --muted:#999; --line:#2c2c2c;
            --ok:#4ade80; --warn:#fbbf24; --bad:#f87171; --accent:#60a5fa; }
  }
  * { box-sizing: border-box; }
  body { background:var(--bg); color:var(--fg); margin:0; padding:16px;
         font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  main { max-width:760px; margin:0 auto; }
  h1 { font-size:1.6rem; margin:1.5rem 0 .25rem; }
  .sub { color:var(--muted); margin:0 0 2rem; }
  #drop { border:2px dashed var(--line); border-radius:10px; padding:3rem 1rem;
          text-align:center; cursor:pointer; transition:border-color .15s; }
  #drop:hover, #drop.over { border-color:var(--accent); }
  #drop p { margin:.4rem 0; color:var(--muted); }
  #file { display:none; }
  .banner { border-radius:8px; padding:.9rem 1rem; margin:1.5rem 0 1rem;
            border-left:4px solid; font-weight:600; }
  .passed { border-color:var(--ok); color:var(--ok); }
  .flagged { border-color:var(--warn); color:var(--warn); }
  .unverified, .error { border-color:var(--bad); color:var(--bad); }
  .banner ul { margin:.5rem 0 0; font-weight:400; }
  table { width:100%; border-collapse:collapse; margin:1rem 0; }
  th, td { text-align:left; padding:.55rem .4rem; border-bottom:1px solid var(--line);
           font-size:.93rem; }
  th { color:var(--muted); font-weight:500; }
  table tr th:first-child { width:38%; }
  #items th:nth-child(2), #items td:nth-child(2) { width:15%; }
  #items th:last-child, #items td:last-child { width:25%; }
  #items th:not(:first-child) { text-align:right; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; }
  h2 { font-size:1rem; margin:1.8rem 0 .3rem; }
  pre { background:var(--line); padding:.9rem; border-radius:8px;
        overflow-x:auto; font-size:.8rem; }
  footer { color:var(--muted); font-size:.85rem; margin:3rem 0 1rem;
           border-top:1px solid var(--line); padding-top:1rem; }
  a { color:var(--accent); }
</style>
</head>
<body>
<main>
  <h1>Invoice Extractor</h1>
  <p class="sub">Upload a PDF invoice. Fields are extracted and the arithmetic
     is checked independently.</p>

  <div id="drop">
    <p><strong>Drop a PDF here</strong></p>
    <p>or click to choose a file</p>
  </div>
  <input type="file" id="file" accept="application/pdf">

  <div id="out"></div>

  <footer>
    Validation reports three states: <strong>passed</strong> (arithmetic
    verified), <strong>flagged</strong> (does not reconcile), and
    <strong>unverified</strong> (not enough fields to check). A document that
    cannot be checked is never reported as correct.
  </footer>
</main>

<script>
const drop = document.getElementById('drop');
const input = document.getElementById('file');
const out = document.getElementById('out');

drop.onclick = () => input.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => {
  e.preventDefault();
  drop.classList.remove('over');
  if (e.dataTransfer.files[0]) send(e.dataTransfer.files[0]);
};
input.onchange = () => { if (input.files[0]) send(input.files[0]); };

const money = (v, c) => v === null || v === undefined
  ? '—' : new Intl.NumberFormat('en-IE',
      {style:'currency', currency: c || 'EUR'}).format(v);
const esc = s => String(s ?? '—').replace(/[<>&]/g,
  c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));

async function send(f) {
  out.innerHTML = '<p style="color:var(--muted)">Extracting…</p>';
  const fd = new FormData();
  fd.append('file', f);
  try {
    const r = await fetch('/api/extract', {method:'POST', body:fd});
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Request failed');
    render(d);
  } catch (err) {
    out.innerHTML = `<div class="banner error">${esc(err.message)}</div>`;
  }
}

function render(d) {
  const inv = d.invoice;
  const cur = inv.currency;
  const label = {passed:'Arithmetic verified',
                 flagged:'Does not reconcile — needs review',
                 unverified:'Could not be verified'}[d.status];

  let banner = `<div class="banner ${d.status}">${label}`;
  if (d.problems.length)
    banner += '<ul>' + d.problems.map(p => `<li>${esc(p)}</li>`).join('') + '</ul>';
  else if (d.checks_run.length)
    banner += `<ul><li>${d.checks_run.map(esc).join('</li><li>')}</li></ul>`;
  banner += '</div>';

  const rows = [
    ['Vendor', esc(inv.vendor_name)],
    ['Invoice number', esc(inv.invoice_number)],
    ['Date', esc(inv.invoice_date)],
    ['Subtotal', money(inv.subtotal, cur)],
    ['Tax', money(inv.tax_amount, cur)],
    ['Total', money(inv.total_amount, cur)],
    ['Line items', inv.line_items.length],
  ].map(([k, v]) => `<tr><th>${k}</th><td class="num">${v}</td></tr>`).join('');

  const items = inv.line_items.map(li =>
    `<tr><td>${esc(li.description)}</td>
         <td class="num">${li.quantity ?? '—'}</td>
         <td class="num">${money(li.total, cur)}</td></tr>`).join('');

  out.innerHTML = banner
    + `<table>${rows}</table>`
    + (inv.line_items.length
        ? `<h2>Line items</h2><table id="items">
             <tr><th>Description</th><th>Qty</th><th>Amount</th></tr>${items}
           </table>` : '')
    + `<h2>JSON</h2><pre>${esc(JSON.stringify(inv, null, 2))}</pre>`;
}
</script>
</body>
</html>"""
