# LT-180 FINAL — konstrukční díly pro Fusion 360

Skript pro Autodesk Fusion 360, který vygeneruje konstrukční (laserem řezané)
díly RC modelu **LT-180** (rozpětí 1800 mm) podle souhrnné metodiky návrhu.

> Pozn.: Pro Fusion 360 neexistuje veřejný MCP server, díly se proto generují
> oficiálním Fusion 360 API skriptem, který spustíte přímo ve Fusionu.

## Použití

1. Ve Fusion 360 otevřete **Utilities → ADD-INS → Scripts and Add-Ins**.
2. Na záložce *Scripts* klikněte na zelené **+** a vyberte složku
   `LT180_parts` z tohoto adresáře.
3. Skript spusťte (**Run**). Vytvoří nový dokument `LT-180 konstrukcni dily`
   s jednou komponentou pro každý typ dílu (počet kusů je v názvu komponenty).
4. Pro laser: pravým tlačítkem na skicu dílu → **Save As DXF**.

## Co skript generuje

### Přepážky trupu (překližka 3 mm, F1 překližka 5 mm)

| Díl | Poloha | Rozměr | Kusů |
|-----|--------|--------|------|
| F1  | 0 mm    | 120×125 | 1 |
| F2  | 95 mm   | 120×140 | 1 |
| F3  | 240 mm  | 120×140 | 1 |
| F4W | 430 mm  | 120×140 | 1 |
| F5W | 650 mm  | 120×140 | 1 |
| F6  | 860 mm  | 100×110 | 1 |
| F7T | 1080 mm | 72×78   | 1 |
| F8T | 1160 mm | 72×78   | 1 |
| F9  | 1250 mm | 48×52   | 1 |

- Ve všech čtyřech rozích výřez **5×5 mm** pro smrkové podélníky 5×5.
- F2–F8T mají odlehčovací otvor (rám 20 mm); F1 (motorová) a F9 jsou plné.
  Odlehčení lze vypnout v konfiguraci (`LIGHTENING = False`).

### Žebra křídla (balza 3 mm, profil Clark Y, hloubka 300 mm)

| Typ | Délka | Kusů celkem (obě poloviny) |
|-----|-------|-----|
| Plné žebro | 300 mm | 12 |
| Krátké žebro (zóna klapky/křidélka) | 235 mm | 22 |
| Žebro klapky/křidélka | 65 mm | 26 (12 klapky + 14 křidélka) |

- Výřezy pro nosníky dle metodiky: **4 nahoře + 3 dole**, šířka **5,2 mm**,
  hloubka **5 mm kolmo k obrysu** (polohy 8/30/52/74 % nahoře,
  30/52/74 % dole — lze upravit v konfiguraci skriptu).
- Krátké žebro = přední část profilu useknutá svisle na 235 mm,
  žebro klapky/křidélka = zadních 65 mm profilu.

Doporučené rozmístění žeber na polovině křídla (rozteč ~55–60 mm; metodika
počty neuvádí, jde o návrh): plná žebra na stanicích 0, 55, 110 (pevný kořen)
a 800, 850, 900 mm (pevný konec); krátká žebra v zóně klapky (110–410 mm)
a křidélka (425–800 mm).

## Hotové DXF pro laser (bez Fusionu)

Složka `dxf/` obsahuje předgenerované soubory (DXF R12, jednotky mm):

- `dxf/dily/` — každý typ dílu samostatně, obrys v počátku (vrstva `CUT`),
- `dxf/narez/` — nářezové plány se všemi kusy dle kusovníku:
  - balza 3 mm, archy 1000×100 mm — 6 archů (60 žeber),
  - překližka 3 mm, arch 600×300 mm — 1 arch (F2–F9),
  - překližka 5 mm, arch 300×200 mm — 1 arch (F1).

V nářezových plánech je navíc vrstva `POPIS` (červená) s názvem dílu pro
gravírování — pokud ji nechcete, v laseru ji vypněte.

Regenerace (např. po úpravě konfigurace v `LT180_parts/LT180_parts.py`
nebo rozměrů archů v `generate_dxf.py`):

```bash
python3 generate_dxf.py
```

## Co skript záměrně negeneruje

Dle zadání jsou vynechány:

- **spoje a kování** — bukové kolíky Ø8, nylonové šrouby M5/M4, uhlíková
  spojka 12/10 (kupované díly),
- **potah a D-box** (balza 1,5 mm),
- **nosníky a podélníky** — smrk 5×5 a 8×8 jsou lišty (polotovar), neřežou se
  laserem; v dílech jsou pro ně jen výřezy,
- **ocasní plochy** — metodika neuvádí jejich rozměry (jen způsob uchycení).

Vzepětí 3°, washout 1° a těžiště 82 mm od náběžné hrany jsou vlastnosti
sestavy/stavby, ne plochých dílů.

## Poznámka před výrobou

Před řezáním celé sady ověřte kompenzaci laseru (spáru) a skutečnou tloušťku
materiálu — výřezy 5×5 / 5,2×5 mm jsou nominální, bez vůle.
