from html import escape
from string import Template

from converter import is_pale


DOCUMENT = Template("""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>$name — Embroidery worksheet</title>
<style>
@page { size: Letter portrait; margin: 12mm; }
* { box-sizing: border-box; }
body { margin: 0; background: #e8edf2; color: #202a37; font: 14px "Segoe UI", sans-serif; }
.controls { position: sticky; top: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
  padding: 12px 20px; color: white; background: #243348; z-index: 1; }
.controls button, .controls select { font: inherit; padding: 4px 9px; }
.controls small { flex-basis: 100%; }
.sheet { background: white; width: min(100%, 215.9mm); min-height: 279.4mm; margin: 20px auto;
  padding: 12mm; box-shadow: 0 2px 14px #26364826; }
body.a4 .sheet { width: min(100%, 210mm); min-height: 297mm; }
header { border-bottom: 2px solid #293a50; padding-bottom: 9px; }
h1 { margin: 0 0 4px; font-size: 24px; overflow-wrap: anywhere; }
p { margin: 4px 0; }
h2 { font-size: 15px; margin: 12px 0 5px; break-after: avoid; }
figure { margin: 10px 0; text-align: center; break-inside: avoid; }
svg { width: min(100%, var(--fit-width)); height: auto; display: block; margin: auto; overflow: visible; }
body.actual svg { width: var(--actual-width); max-width: none; }
figcaption { margin-top: 4px; color: #475569; font-size: 11px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th, td { text-align: left; border-bottom: 1px solid #dbe2e9; padding: 3px 6px; }
th:first-child, td:first-child { width: 48px; }
th:last-child, td:last-child { text-align: right; }
.swatch { display: inline-block; width: 12px; height: 12px; margin-right: 7px; vertical-align: -2px;
  border: 1px solid #5d6976; }
@media print {
  body, body.a4 { background: white; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  .controls { display: none; }
  .sheet, body.a4 .sheet { width: auto; min-height: 0; padding: 0; margin: 0; box-shadow: none; }
}
</style>
<style id="page-size"></style>
<div class="controls">
  <button type="button" onclick="window.print()">Print / Save as PDF…</button>
  <label>Paper <select id="paper"><option>Letter</option><option>A4</option></select></label>
  <label>Design scale <select id="scale"><option value="fit">Fit worksheet</option>
    <option value="actual">Actual size (1:1)</option></select></label>
  <small id="print-note" aria-live="polite"></small>
</div>
<main class="sheet">
  <header>
    <h1>$name</h1>
    <p>$dimensions · $stitches stitches · $sections thread sections</p>
  </header>
  <figure>
    $diagram
    <figcaption id="diagram-scale">Scaled to fit the worksheet</figcaption>
  </figure>
  <h2>Thread order</h2>
  <table>
    <thead><tr><th scope="col">Step</th><th scope="col">Color</th>
      <th scope="col">Thread details</th><th scope="col">Stitches</th></tr></thead>
    <tbody>$rows</tbody>
  </table>
</main>
<script>
const paper = document.getElementById('paper');
const scale = document.getElementById('scale');
const note = document.getElementById('print-note');
const actualWidth = $width;
const actualHeight = $height;
function updateLayout() {
  const a4 = paper.value === 'A4';
  document.body.classList.toggle('a4', a4);
  document.getElementById('page-size').textContent =
    '@page { size: ' + (a4 ? 'A4' : 'Letter') + ' portrait; margin: 12mm; }';
  const fits = actualWidth <= (a4 ? 186 : 191.9) && actualHeight <= (a4 ? 235 : 218);
  scale.options[1].disabled = !fits;
  if (!fits) scale.value = 'fit';
  const actual = scale.value === 'actual';
  document.body.classList.toggle('actual', actual);
  document.getElementById('diagram-scale').textContent =
    actual ? 'Actual size (1:1)' : 'Scaled to fit the worksheet';
  note.textContent = actual ? 'Set print scale to 100% and match the paper size.'
    : fits ? '' : 'This design is too large for an actual-size worksheet on this paper.';
}
paper.addEventListener('change', updateLayout);
scale.addEventListener('change', updateLayout);
updateLayout();
</script>
</html>
""")


def stitch_diagram(design):
    left, top, right, bottom = design.bounds
    padding = 10
    width, height = right - left + 2 * padding, bottom - top + 2 * padding
    fit_width = min(184, 110 * width / height)
    parts = [f'<svg role="img" aria-label="Stitch diagram" '
             f'viewBox="{left-padding:g} {top-padding:g} {width:g} {height:g}" '
             f'style="--fit-width:{fit_width:.4f}mm;--actual-width:{width/10:.4f}mm">']
    for index, points in design.runs:
        color = design.pattern.threadlist[index].hex_color()
        if len(points) == 2 and points[0] == points[1]:
            x, y = points[0]
            parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="1.5" fill="{color}" '
                         'stroke="#68717c" stroke-width=".4"/>')
            continue
        path = " ".join(f"{x:.3f},{y:.3f}" for x, y in points)
        if is_pale(color):
            parts.append(f'<polyline points="{path}" fill="none" stroke="#68717c" '
                         'stroke-width="3.6" stroke-linejoin="round" stroke-linecap="round"/>')
        parts.append(f'<polyline points="{path}" fill="none" stroke="{color}" '
                     'stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')
    parts.append("</svg>")
    return "".join(parts), width / 10, height / 10


def write_worksheet(design, name, destination):
    diagram, width, height = stitch_diagram(design)
    left, top, right, bottom = design.bounds
    dimensions = f"{(right-left)/10:.1f} × {(bottom-top)/10:.1f} mm"
    rows = []
    for step, (index, count) in enumerate(design.sections, 1):
        thread = design.pattern.threadlist[index]
        color = thread.hex_color()
        detail = " · ".join(str(value) for value in
                            (thread.brand, thread.catalog_number, thread.description) if value)
        if index in design.estimated and not detail:
            detail = "Assigned preview color"
        rows.append(f'<tr><td>{step}</td><td><span class="swatch" style="background:{color}"></span>'
                    f'{color.upper()}</td><td>{escape(detail)}</td><td>{count:,}</td></tr>')
    destination.write_text(DOCUMENT.substitute(
        name=escape(name), dimensions=dimensions, stitches=f"{design.count:,}",
        sections=len(design.sections), diagram=diagram, rows="".join(rows), width=width, height=height,
    ), encoding="utf-8")
