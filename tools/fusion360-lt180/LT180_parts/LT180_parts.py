# LT180_parts.py
# Skript pro Autodesk Fusion 360 (Utilities -> ADD-INS -> Scripts and Add-Ins -> +)
#
# Vygeneruje konstrukcni dily RC modelu LT-180 FINAL (rozpeti 1800 mm) podle
# souhrnne metodiky navrhu:
#   - prepazky trupu F1-F9 s rohovymi vyrezy 5x5 mm pro smrkove podelniky
#   - zebra kridla (profil Clark Y): plna 300 mm, kratka 235 mm,
#     zebra klapek/kridelek 65 mm
#   - vyrezy v zebrech pro nosniky: 4 nahore + 3 dole, sirka 5,2 mm,
#     hloubka 5 mm kolmo k obrysu
#
# Zamerne NEobsahuje: spojovaci prvky (koliky, srouby, spojku), potah ani
# D-box (balza 1,5 mm), smrkove liste (poloTovar), ocasni plochy (metodika
# neuvadi jejich rozmery).
#
# Vsechny rozmery v konfiguraci jsou v mm; Fusion API interne pracuje v cm.

import math
import traceback

try:
    import adsk.core
    import adsk.fusion
    _IN_FUSION = True
except ImportError:
    _IN_FUSION = False  # umoznuje lokalni test geometrie mimo Fusion

MM = 0.1  # prevod mm -> cm (interni jednotky Fusion API)

# ---------------------------------------------------------------------------
# Konfigurace (mm)
# ---------------------------------------------------------------------------

CHORD = 300.0             # hloubka kridla / plne zebro
SHORT_RIB_CHORD = 235.0   # kratke zebro (zona klapek a kridelek)
CTRL_RIB_LEN = 65.0       # zebro klapky/kridelka (zadni cast profilu)

BALSA_T = 3.0             # tloustka zeber (balza 3 mm)
PLY_T = 3.0               # tloustka prepazek (preklizka 3 mm)
F1_T = 5.0                # F1 = motorova prepazka (preklizka 5 mm)

# Vyrezy pro nosniky v zebrech (dle metodiky: sirka 5,2 mm, hloubka 5 mm
# kolmo k obrysu; 4 nahore, 3 dole). Polohy = vzdalenost od nabezne hrany.
NOTCH_W = 5.2
NOTCH_D = 5.0
TOP_NOTCH_X = [24.0, 90.0, 156.0, 222.0]     # 8 %, 30 %, 52 %, 74 % hloubky
BOTTOM_NOTCH_X = [90.0, 156.0, 222.0]        # 30 %, 52 %, 74 % hloubky

# Rohove vyrezy prepazek pro podelniky smrk 5x5 mm
LONGERON = 5.0

# Odlehcovaci otvor prepazek (ramova konstrukce trupu); okraj ramu v mm.
# F1 (motorova) a F9 (zaverna) zustavaji plne.
LIGHTENING = True
LIGHTENING_MARGIN = 20.0

# Prepazky: (nazev, sirka, vyska, tloustka, odlehcit, pocet kusu)
BULKHEADS = [
    ('F1',  120.0, 125.0, F1_T,  False, 1),
    ('F2',  120.0, 140.0, PLY_T, True,  1),
    ('F3',  120.0, 140.0, PLY_T, True,  1),
    ('F4W', 120.0, 140.0, PLY_T, True,  1),
    ('F5W', 120.0, 140.0, PLY_T, True,  1),
    ('F6',  100.0, 110.0, PLY_T, True,  1),
    ('F7T',  72.0,  78.0, PLY_T, True,  1),
    ('F8T',  72.0,  78.0, PLY_T, True,  1),
    ('F9',   48.0,  52.0, PLY_T, False, 1),
]

# Pocty zeber (obe poloviny kridla; roztec ~55-60 mm, viz README)
QTY_FULL_RIB = 12   # plna zebra 300 mm
QTY_SHORT_RIB = 22  # kratka zebra 235 mm
QTY_CTRL_RIB = 26   # zebra klapek (12) + kridelek (14)

# ---------------------------------------------------------------------------
# Profil Clark Y (x, y_horni, y_dolni v % hloubky)
# ---------------------------------------------------------------------------

CLARK_Y = [
    (0.0,   3.50, 3.50),
    (1.25,  5.45, 1.93),
    (2.5,   6.50, 1.47),
    (5.0,   7.90, 0.93),
    (7.5,   8.85, 0.63),
    (10.0,  9.60, 0.42),
    (15.0, 10.68, 0.15),
    (20.0, 11.36, 0.03),
    (30.0, 11.70, 0.00),
    (40.0, 11.40, 0.00),
    (50.0, 10.52, 0.00),
    (60.0,  9.15, 0.00),
    (70.0,  7.35, 0.00),
    (80.0,  5.22, 0.00),
    (90.0,  2.80, 0.00),
    (95.0,  1.49, 0.00),
    (100.0, 0.12, 0.00),
]

# ---------------------------------------------------------------------------
# Geometrie (ciste funkce, testovatelne mimo Fusion)
# ---------------------------------------------------------------------------

def _catmull_rom(pts, spacing=2.0):
    """Vyhladi lomenou caru Catmull-Rom splinem, vzorkovani ~spacing mm."""
    if len(pts) < 3:
        return list(pts)
    ext = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        seg = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        steps = max(1, int(math.ceil(seg / spacing)))
        for s in range(steps):
            t = s / float(steps)
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(pts[-1])
    return out


def _surface(upper=True, chord=CHORD):
    """Horni/dolni obrys profilu od nabezne k odtokove hrane (mm)."""
    idx = 1 if upper else 2
    ctrl = [(p[0] * chord / 100.0, p[idx] * chord / 100.0) for p in CLARK_Y]
    return _catmull_rom(ctrl, spacing=2.0)


def _y_at(pts, x):
    """Linearni interpolace y na polylinii serazene podle x."""
    if x <= pts[0][0]:
        return pts[0][1]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= x <= x1 and x1 > x0:
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return pts[-1][1]


def _insert_notch(pts, xc, width, depth, upper):
    """Vlozi do obrysu vyrez pro nosnik kolmo k mistnimu obrysu."""
    half = width / 2.0
    xl, xr = xc - half, xc + half
    yl, yr = _y_at(pts, xl), _y_at(pts, xr)
    # tecna v miste vyrezu
    ya, yb = _y_at(pts, xc - 1.0), _y_at(pts, xc + 1.0)
    tx, ty = 2.0, yb - ya
    tl = math.hypot(tx, ty)
    tx, ty = tx / tl, ty / tl
    # normala smerem dovnitr zebra
    if upper:
        nx, ny = ty, -tx
    else:
        nx, ny = -ty, tx
    notch = [
        (xl, yl),
        (xl + nx * depth, yl + ny * depth),
        (xr + nx * depth, yr + ny * depth),
        (xr, yr),
    ]
    before = [p for p in pts if p[0] < xl]
    after = [p for p in pts if p[0] > xr]
    return before + notch + after


def _notched_surface(upper, chord, notch_xs):
    pts = _surface(upper, chord)
    for xc in sorted(notch_xs, reverse=True):
        if xc + NOTCH_W / 2.0 < chord - 1.0:
            pts = _insert_notch(pts, xc, NOTCH_W, NOTCH_D, upper)
    return pts


def _dedupe(pts, tol=0.02):
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append(p)
    if len(out) > 2 and math.hypot(out[0][0] - out[-1][0],
                                   out[0][1] - out[-1][1]) <= tol:
        out.pop()
    return out


def _close_loop(top, bottom):
    """Uzavreny obrys: horni LE->TE + dolni TE->LE."""
    return _dedupe(list(top) + list(reversed(bottom)))


def _clip_max_x(pts, xmax):
    kept = [p for p in pts if p[0] < xmax]
    kept.append((xmax, _y_at(pts, xmax)))
    return kept


def _clip_min_x(pts, xmin):
    kept = [p for p in pts if p[0] > xmin]
    return [(xmin, _y_at(pts, xmin))] + kept


def rib_full():
    """Plne zebro 300 mm se vsemi vyrezy pro nosniky."""
    top = _notched_surface(True, CHORD, TOP_NOTCH_X)
    bottom = _notched_surface(False, CHORD, BOTTOM_NOTCH_X)
    return _close_loop(top, bottom)


def rib_short():
    """Kratke zebro 235 mm (zona klapek/kridelek), svisla zadni hrana."""
    top = _clip_max_x(_notched_surface(True, CHORD, TOP_NOTCH_X),
                      SHORT_RIB_CHORD)
    bottom = _clip_max_x(_notched_surface(False, CHORD, BOTTOM_NOTCH_X),
                         SHORT_RIB_CHORD)
    return _close_loop(top, bottom)


def rib_control():
    """Zebro klapky/kridelka: zadnich 65 mm profilu, svisla predni hrana."""
    x0 = CHORD - CTRL_RIB_LEN
    top = _clip_min_x(_surface(True, CHORD), x0)
    bottom = _clip_min_x(_surface(False, CHORD), x0)
    return _close_loop(top, bottom)


def bulkhead_outline(w, h):
    """Obdelnikova prepazka s rohovymi vyrezy 5x5 mm pro podelniky."""
    n = LONGERON
    return [
        (n, 0.0), (w - n, 0.0),
        (w - n, n), (w, n),
        (w, h - n), (w - n, h - n),
        (w - n, h), (n, h),
        (n, h - n), (0.0, h - n),
        (0.0, n), (n, n),
    ]


def bulkhead_hole(w, h):
    """Odlehcovaci otvor (None, pokud je prepazka na otvor mala)."""
    m = LIGHTENING_MARGIN
    if not LIGHTENING or w - 2 * m < 30.0 or h - 2 * m < 30.0:
        return None
    return [(m, m), (w - m, m), (w - m, h - m), (m, h - m)]


# ---------------------------------------------------------------------------
# Tvorba dilu ve Fusion 360
# ---------------------------------------------------------------------------

def _new_component(root, name, tx_mm, ty_mm):
    transform = adsk.core.Matrix3D.create()
    transform.translation = adsk.core.Vector3D.create(tx_mm * MM, ty_mm * MM, 0)
    occ = root.occurrences.addNewComponent(transform)
    occ.component.name = name
    return occ.component


def _add_polygon(sketch, pts_mm):
    lines = sketch.sketchCurves.sketchLines
    pts = _dedupe(pts_mm)
    p3d = [adsk.core.Point3D.create(x * MM, y * MM, 0) for (x, y) in pts]
    for i in range(len(p3d)):
        lines.addByTwoPoints(p3d[i], p3d[(i + 1) % len(p3d)])


def _extrude_part(comp, outline, thickness_mm, hole=None):
    sketch = comp.sketches.add(comp.xYConstructionPlane)
    sketch.isComputeDeferred = True
    _add_polygon(sketch, outline)
    if hole:
        _add_polygon(sketch, hole)
    sketch.isComputeDeferred = False
    # profil s nejvetsi plochou = obrys minus otvor
    best = None
    best_area = -1.0
    for prof in sketch.profiles:
        area = prof.areaProperties().area
        if area > best_area:
            best_area = area
            best = prof
    ext = comp.features.extrudeFeatures
    ext_input = ext.createInput(
        best, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ext_input.setDistanceExtent(
        False, adsk.core.ValueInput.createByReal(thickness_mm * MM))
    ext.add(ext_input)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent
        root.name = 'LT-180 konstrukcni dily'

        made = 0

        # --- prepazky trupu (rada u y = 0) ---
        x = 0.0
        for (name, w, h, t, lighten, qty) in BULKHEADS:
            label = '{} ({}x, preklizka {:g} mm, {:g}x{:g})'.format(
                name, qty, t, w, h)
            comp = _new_component(root, label, x, 0.0)
            hole = bulkhead_hole(w, h) if lighten else None
            _extrude_part(comp, bulkhead_outline(w, h), t, hole)
            x += w + 20.0
            made += 1

        # --- zebra kridla (rady pod prepazkami) ---
        ribs = [
            ('Zebro plne 300 ({}x, balza {:g} mm)'.format(
                QTY_FULL_RIB, BALSA_T), rib_full(), 0.0, -80.0),
            ('Zebro kratke 235 ({}x, balza {:g} mm)'.format(
                QTY_SHORT_RIB, BALSA_T), rib_short(), 340.0, -80.0),
            ('Zebro klapky-kridelka 65 ({}x, balza {:g} mm)'.format(
                QTY_CTRL_RIB, BALSA_T), rib_control(), 620.0, -80.0),
        ]
        for (label, outline, px, py) in ribs:
            comp = _new_component(root, label, px, py)
            _extrude_part(comp, outline, BALSA_T)
            made += 1

        ui.messageBox(
            'LT-180: vygenerovano {} typu dilu.\n\n'
            'Prepazky F1-F9 (rohove vyrezy 5x5 mm pro podelniky)\n'
            'Zebra: plne 300 / kratke 235 / klapka-kridelko 65 mm\n'
            'Vyrezy pro nosniky: 4 nahore + 3 dole, 5,2 x 5 mm.\n\n'
            'Pocty kusu jsou v nazvech komponent. Pro laser exportujte '
            'skici dilu jako DXF.'.format(made))
    except Exception:
        if ui:
            ui.messageBox('Selhani skriptu:\n{}'.format(traceback.format_exc()))
