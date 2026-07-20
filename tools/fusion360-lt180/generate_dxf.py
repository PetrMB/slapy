# generate_dxf.py
# Samostatny generator DXF (R12) pro laserove rezani dilu LT-180.
# Nepotrebuje Fusion 360 ani zadne knihovny - spustit: python3 generate_dxf.py
#
# Vystup (slozka dxf/):
#   - dily/<nazev>.dxf          ... kazdy typ dilu samostatne (obrys v pocatku)
#   - narez/<material>_arch_N.dxf ... narezove plany se vsemi kusy
#
# Vrstvy: CUT (rez, bila), POPIS (gravirovani nazvu, cervena - lze vypnout).
# Geometrie dilu je prevzata z LT180_parts.py, takze DXF vzdy odpovida
# skriptu pro Fusion.

import os
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'lt180', os.path.join(_HERE, 'LT180_parts', 'LT180_parts.py'))
lt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lt)

# ---------------------------------------------------------------------------
# Konfigurace narezu (mm)
# ---------------------------------------------------------------------------

GAP = 4.0          # mezera mezi dily
MARGIN = 5.0       # okraj archu
ENGRAVE_LABELS = True

# Dostupne formaty materialu: (nazev souboru, sirka, vyska archu)
SHEETS = {
    'balza3': (1000.0, 100.0),      # standardni prkenko balzy 3 mm
    'preklizka3': (600.0, 300.0),
    'preklizka5': (300.0, 200.0),
}

# ---------------------------------------------------------------------------
# Kusovnik: (nazev, obrys, otvory, material, pocet)
# ---------------------------------------------------------------------------

def build_parts():
    parts = []
    for (name, w, h, t, lighten, qty) in lt.BULKHEADS:
        material = 'preklizka5' if t == lt.F1_T else 'preklizka3'
        hole = lt.bulkhead_hole(w, h) if lighten else None
        holes = [hole] if hole else []
        parts.append((name, lt.bulkhead_outline(w, h), holes, material, qty))
    parts.append(('zebro-plne-300', lt.rib_full(), [], 'balza3',
                  lt.QTY_FULL_RIB))
    parts.append(('zebro-kratke-235', lt.rib_short(), [], 'balza3',
                  lt.QTY_SHORT_RIB))
    parts.append(('zebro-klapka-65', lt.rib_control(), [], 'balza3',
                  lt.QTY_CTRL_RIB))
    return parts

# ---------------------------------------------------------------------------
# Zapis DXF R12
# ---------------------------------------------------------------------------

def _dxf_header(out):
    out += ['0', 'SECTION', '2', 'TABLES',
            '0', 'TABLE', '2', 'LAYER', '70', '2',
            '0', 'LAYER', '2', 'CUT', '70', '0', '62', '7',
            '6', 'CONTINUOUS',
            '0', 'LAYER', '2', 'POPIS', '70', '0', '62', '1',
            '6', 'CONTINUOUS',
            '0', 'ENDTAB', '0', 'ENDSEC',
            '0', 'SECTION', '2', 'ENTITIES']
    return out


def _dxf_polyline(out, pts, layer='CUT'):
    out += ['0', 'POLYLINE', '8', layer, '66', '1', '70', '1']
    for (x, y) in pts:
        out += ['0', 'VERTEX', '8', layer,
                '10', '%.3f' % x, '20', '%.3f' % y]
    out += ['0', 'SEQEND']
    return out


def _dxf_text(out, x, y, height, text, layer='POPIS'):
    out += ['0', 'TEXT', '8', layer,
            '10', '%.3f' % x, '20', '%.3f' % y,
            '40', '%.3f' % height, '1', text]
    return out


def _dxf_save(path, out):
    out += ['0', 'ENDSEC', '0', 'EOF']
    with open(path, 'w') as f:
        f.write('\n'.join(out) + '\n')


def _translated(pts, dx, dy):
    return [(x + dx, y + dy) for (x, y) in pts]


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

# ---------------------------------------------------------------------------
# Jednoduche radkove (shelf) skladani dilu na archy
# ---------------------------------------------------------------------------

def pack(instances, sheet_w, sheet_h):
    """instances: [(name, outline, holes)] -> [ [ (name, outline, holes, x, y) ] ]"""
    # normalizace do pocatku + razeni podle vysky
    norm = []
    for (name, outline, holes) in instances:
        x0, y0, x1, y1 = _bbox(outline)
        norm.append((y1 - y0, x1 - x0, name,
                     _translated(outline, -x0, -y0),
                     [_translated(h, -x0, -y0) for h in holes]))
    norm.sort(key=lambda r: -r[0])

    sheets = []
    cur, cx, cy, row_h = [], MARGIN, MARGIN, 0.0
    for (ph, pw, name, outline, holes) in norm:
        if pw > sheet_w - 2 * MARGIN or ph > sheet_h - 2 * MARGIN:
            raise ValueError('Dil %s (%.0fx%.0f) se nevejde na arch %gx%g'
                             % (name, pw, ph, sheet_w, sheet_h))
        if cx + pw > sheet_w - MARGIN:            # novy radek
            cx = MARGIN
            cy += row_h + GAP
            row_h = 0.0
        if cy + ph > sheet_h - MARGIN:            # novy arch
            sheets.append(cur)
            cur, cx, cy, row_h = [], MARGIN, MARGIN, 0.0
        cur.append((name, _translated(outline, cx, cy),
                    [_translated(h, cx, cy) for h in holes], cx, cy))
        cx += pw + GAP
        row_h = max(row_h, ph)
    if cur:
        sheets.append(cur)
    return sheets

# ---------------------------------------------------------------------------
# Hlavni beh
# ---------------------------------------------------------------------------

def main():
    parts = build_parts()

    part_dir = os.path.join(_HERE, 'dxf', 'dily')
    layout_dir = os.path.join(_HERE, 'dxf', 'narez')
    os.makedirs(part_dir, exist_ok=True)
    os.makedirs(layout_dir, exist_ok=True)

    # jednotlive dily
    for (name, outline, holes, material, qty) in parts:
        x0, y0, _, _ = _bbox(outline)
        out = _dxf_header([])
        _dxf_polyline(out, _translated(outline, -x0, -y0))
        for h in holes:
            _dxf_polyline(out, _translated(h, -x0, -y0))
        _dxf_save(os.path.join(part_dir, name + '.dxf'), out)

    # narezove plany po materialech
    summary = []
    for material, (sw, sh) in SHEETS.items():
        instances = []
        for (name, outline, holes, mat, qty) in parts:
            if mat == material:
                instances += [(name, outline, holes)] * qty
        if not instances:
            continue
        sheets = pack(instances, sw, sh)
        for i, sheet in enumerate(sheets, 1):
            out = _dxf_header([])
            for (name, outline, holes, px, py) in sheet:
                _dxf_polyline(out, outline)
                for h in holes:
                    _dxf_polyline(out, h)
                if ENGRAVE_LABELS:
                    bx0, by0, bx1, by1 = _bbox(outline)
                    _dxf_text(out, bx0 + 6.0, by0 + 3.0,
                              min(5.0, (by1 - by0) * 0.25), name)
            path = os.path.join(layout_dir,
                                '%s_arch_%d.dxf' % (material, i))
            _dxf_save(path, out)
        summary.append((material, sw, sh, len(instances), len(sheets)))

    print('Jednotlive dily: %d souboru -> dxf/dily/' % len(parts))
    for (material, sw, sh, n, ns) in summary:
        print('Narez %-11s (%4gx%g mm): %2d kusu na %d arch(y)'
              % (material, sw, sh, n, ns))


if __name__ == '__main__':
    main()
