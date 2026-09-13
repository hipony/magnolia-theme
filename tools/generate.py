#!/usr/bin/env python3
"""Magnolia theme generator.

- Lints the VS Code theme against palette/palette.json (no stray colors)
- Emits Konsole .colorscheme, KDE .colors, Kvantum, Plasma, and GTK themes, the opencode theme, and a Mailspring theme into exports/
- Regenerates the palette table in README.md

Zero dependencies, Python 3.8+. Run: python3 tools/generate.py
"""
import gzip
import json
import re
import shutil
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PALETTE_PATH = ROOT / "palette" / "palette.json"
THEME_PATH = ROOT / "themes" / "Magnolia Theme-color-theme.json"
README_PATH = ROOT / "README.md"
EXPORTS = ROOT / "exports"

README_START = "<!-- generated:palette:start -->"
README_END = "<!-- generated:palette:end -->"


def load_palette():
    p = json.loads(PALETTE_PATH.read_text())
    p["_by_name"] = {name: entry["hex"] for name, entry in p["colors"].items()}
    return p


def hex_base(hexcolor):
    """Return (6-digit base, alpha) of any #RGB/#RGBA/#RRGGBB/#RRGGBBAA string."""
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    elif len(h) == 4:
        h = "".join(c * 2 for c in h)
    return h[:6].lower(), (h[6:].lower() if len(h) == 8 else None)


# ---------- lint ----------

def collect_hexes(node, out):
    if isinstance(node, dict):
        for v in node.values():
            collect_hexes(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_hexes(v, out)
    elif isinstance(node, str) and re.fullmatch(r"#[0-9a-fA-F]{3,8}", node):
        out.append(node.lower())


ANSI_SLOTS = ["Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"]


def lint_ansi(palette, theme):
    """Cross-check the 16 terminal.ansi* keys against palette ansi mapping."""
    ref, ansi = palette["_by_name"], palette["ansi"]
    problems = []
    for i, slot in enumerate(ANSI_SLOTS):
        for prefix, expected_name in ((f"terminal.ansi{slot}", ansi["normal"][i]),
                                      (f"terminal.ansiBright{slot}", ansi["bright"][i])):
            actual = theme["colors"].get(prefix, "").lower()
            expected = ref[expected_name].lower()
            if actual != expected:
                problems.append(f"  {prefix}: theme={actual or '<missing>'}  palette[{expected_name}]={expected}")
    if problems:
        print("LINT: terminal ANSI keys deviate from palette 'ansi' mapping:")
        print("\n".join(problems))
        return False
    print("LINT: terminal ANSI 16 matches the palette mapping")
    return True


def lint(palette):
    theme = json.loads(THEME_PATH.read_text())
    allowed = {hex_base(h)[0] for h in palette["_by_name"].values()}
    allowlist = {h.lower() for h in palette["lint"]["allowlist"]}
    strays = {}

    for section in ("colors", "semanticTokenColors", "tokenColors"):
        hexes = []
        collect_hexes(theme.get(section), hexes)
        for hx in hexes:
            if hx in allowlist:
                continue
            base, alpha = hex_base(hx)
            if base not in allowed:
                strays.setdefault(hx, {"sections": set(), "count": 0})
                strays[hx]["count"] += 1
                strays[hx]["sections"].add(section)

    if strays:
        print("LINT: colors outside palette/palette.json:")
        for hx, info in sorted(strays.items()):
            print(f"  {hx}  x{info['count']}  in: {', '.join(sorted(info['sections']))}")
        return False
    print(f"LINT: OK ({len(theme['colors'])} UI keys, all colors trace to the palette)")
    return lint_ansi(palette, theme)


# ---------- export lint ----------

# Colors that legitimately stay in Plasma SVGs outside the palette: shadow
# gradients (#000000), invisible margin/inset/shadow hint fills, and Inkscape
# editor metadata (pagecolor, bordercolor, grid color).
PLASMA_BENIGN = {
    "000000", "00ff00", "ff00ff", "9a06ff", "4e9a06", "00ffff", "0000ff", "800080",
    "ffcc00", "ff6600", "ff0000", "008000", "ff2a2a", "00626d", "023812", "007584",
    "ed333b", "8d8dff", "b0dba0", "cc0000", "a8a8a8",
}

# Kvantum window-decoration SVG: black shadow gradients only.
KVANTUM_BENIGN = {"000000"}

# GTK CSS: pure black is used for text shadows and asset outlines.
GTK_BENIGN = {"000000"}


def png_colors(data):
    """Set of '#rrggbb' colors in a non-interlaced 8-bit PNG (colortype 2/6), else None."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat = 8, b""
    width = height = ct = depth = interlace = 0
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height = int.from_bytes(body[0:4], "big"), int.from_bytes(body[4:8], "big")
            depth, ct, interlace = body[8], body[9], body[12]
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if depth != 8 or ct not in (2, 6) or interlace != 0 or not idat:
        return None
    channels = 3 if ct == 2 else 4
    raw = zlib.decompress(idat)
    stride = width * channels
    colors = set()
    prev = bytearray(stride)
    for y in range(height):
        off = y * (stride + 1)
        ftype, cur = raw[off], bytearray(raw[off + 1:off + 1 + stride])
        for x in range(stride):
            a = cur[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if ftype == 1:
                cur[x] = (cur[x] + a) & 0xFF
            elif ftype == 2:
                cur[x] = (cur[x] + b) & 0xFF
            elif ftype == 3:
                cur[x] = (cur[x] + (a + b) // 2) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[x] = (cur[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 0xFF
        for x in range(0, stride, channels):
            colors.add(f"{cur[x]:02x}{cur[x+1]:02x}{cur[x+2]:02x}")
        prev = cur
    return colors


def lint_exports(palette):
    """All export colors must trace to the palette (icons exempt in Plasma)."""
    ref = palette["_by_name"]
    allowed_hex = {h.lstrip("#").lower() for h in ref.values()}
    allowed_rgb = {to_rgb_dec(h) for h in ref.values()}
    problems = []

    for rel in (f"kde/{palette['name']}.colors", f"konsole/{palette['name']}.colorscheme"):
        text = (EXPORTS / rel).read_text()
        for value in re.findall(r"^Color=([\d,]+)", text, re.M):
            if value not in allowed_rgb:
                problems.append(f"  {rel}: Color={value} is not a palette color")

    for name in (f"{palette['name']}.kvconfig", f"{palette['name']}.svg"):
        path = EXPORTS / "kvantum" / palette["name"] / name
        if not path.exists():
            continue
        for hx in {m.lower() for m in re.findall(r"#([0-9a-fA-F]{6})", path.read_text())}:
            if hx not in allowed_hex and hx not in KVANTUM_BENIGN:
                problems.append(f"  kvantum/{name}: #{hx} is not a palette color")

    k = palette["plasmaTheme"]
    banned = {rgb.lower() for rgb in k["svgColorMap"]}
    for m in k.get("svgFileColorMap", {}).values():
        banned |= {rgb.lower() for rgb in m}
    plasma_dir = EXPORTS / "plasma" / palette["name"]
    for path in plasma_dir.rglob("*"):
        if path.suffix not in (".svg", ".svgz"):
            continue
        raw = gzip.decompress(path.read_bytes()) if path.suffix == ".svgz" else path.read_bytes()
        rel = path.relative_to(plasma_dir).as_posix()
        for hx in {m.lower() for m in re.findall(r"#([0-9a-fA-F]{6})", raw.decode("utf-8", "replace"))}:
            if hx in banned:
                problems.append(f"  plasma/{rel}: #{hx} should have been remapped (regenerate)")
            elif hx not in allowed_hex and hx not in PLASMA_BENIGN and not rel.startswith("icons/"):
                problems.append(f"  plasma/{rel}: stray #{hx}")

    g = palette["gtkTheme"]
    gtk_banned = {rgb.lower() for rgb in g["cssColorMap"]} | {rgb.lower() for rgb in g.get("pngColorMap", {})}
    gtk_dir = EXPORTS / "gtk" / palette["name"]
    for path in gtk_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(gtk_dir).as_posix()
        if path.suffix == ".png":
            pixels = png_colors(path.read_bytes())
            if pixels is None:
                continue
            for px in pixels:
                if f"#{px}" in gtk_banned:
                    problems.append(f"  gtk/{rel}: pixel #{px} should have been remapped (regenerate)")
            continue
        if path.suffix in (".jpg", ".jpeg") or path.name == "thumbnail.png":
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        for hx in {m.lower() for m in re.findall(r"#([0-9a-fA-F]{6})\b", text)}:
            if f"#{hx}" in gtk_banned:
                problems.append(f"  gtk/{rel}: #{hx} should have been remapped (regenerate)")
            elif hx not in allowed_hex and hx not in GTK_BENIGN:
                problems.append(f"  gtk/{rel}: stray #{hx}")

    if problems:
        print("LINT: exports deviate from the palette:")
        print("\n".join(problems))
        return False
    print("LINT: exports trace to the palette")
    return True


# ---------- Konsole ----------

def to_rgb_dec(hexcolor):
    base, _ = hex_base(hexcolor)
    r, g, b = (int(base[i:i + 2], 16) for i in (0, 2, 4))
    return f"{r},{g},{b}"


def emit_konsole(palette):
    p = palette
    ref = p["_by_name"]
    ansi = p["ansi"]
    k = p["konsole"]

    def color(idx, variant=""):
        key = {"": "normal", "Intense": "bright", "Faint": "normal"}[variant]
        return ref[ansi[key][idx]]

    lines = [
        "[General]",
        f"Description={p['name']}",
        "Opacity=1",
        "Blur=false",
        "Wallpaper=",
        "ColorRandomization=false",
        "",
    ]
    for key, name in (("Background", k["background"]), ("BackgroundIntense", k["backgroundIntense"]),
                      ("BackgroundFaint", k["backgroundFaint"]), ("Foreground", k["foreground"]),
                      ("ForegroundIntense", k["foregroundIntense"]), ("ForegroundFaint", k["foregroundFaint"])):
        lines += [f"[{key}]", f"Color={to_rgb_dec(ref[name])}", ""]
    for variant in ("", "Intense", "Faint"):
        for i in range(8):
            name = color(i, variant)
            lines += [f"[Color{i}{variant}]", f"Color={to_rgb_dec(name)}", ""]
    text = "\n".join(lines).rstrip() + "\n"

    out = EXPORTS / "konsole" / f"{p['name']}.colorscheme"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


# ---------- KDE ----------

COLOR_EFFECT_DISABLED = """\
[ColorEffects:Disabled]
ChangeSelectionColor=
ColorAmount=0
ColorEffect=0
ContrastAmount=0.65
ContrastEffect=1
Enabled=
IntensityAmount=0.35
IntensityEffect=2
"""

COLOR_EFFECT_INACTIVE = """\
[ColorEffects:Inactive]
ChangeSelectionColor=
ColorAmount=0.025
ColorEffect=0
ContrastAmount=0.1
ContrastEffect=0
Enabled=
IntensityAmount=0
IntensityEffect=0
"""


def emit_kde(palette):
    p = palette
    ref = p["_by_name"]
    k = p["kde"]

    def dec(name):
        return to_rgb_dec(ref[name])

    accent = k["accent"]
    accent_text = k.get("accentText", accent)
    hover = k["accentHover"]
    selection = k["selectionBackground"]
    selection_alt = k["selectionAlternateBackground"]
    selection_text = k["selectionText"]

    def group(background, alternate, text=None, inactive=None):
        text = text or k["text"]
        inactive = inactive or k["textInactive"]
        return "\n".join([
            f"BackgroundAlternate={dec(alternate)}",
            f"BackgroundNormal={dec(background)}",
            f"DecorationFocus={dec(accent)}",
            f"DecorationHover={dec(hover)}",
            f"ForegroundActive={dec(accent_text)}",
            f"ForegroundInactive={dec(inactive)}",
            f"ForegroundLink={dec(k['link'])}",
            f"ForegroundNegative={dec(k['negative'])}",
            f"ForegroundNeutral={dec(k['neutral'])}",
            f"ForegroundNormal={dec(text)}",
            f"ForegroundPositive={dec(k['positive'])}",
            f"ForegroundVisited={dec(k['visited'])}",
        ])

    def selection_group():
        return "\n".join([
            f"BackgroundAlternate={dec(selection_alt)}",
            f"BackgroundNormal={dec(selection)}",
            f"DecorationFocus={dec(accent)}",
            f"DecorationHover={dec(hover)}",
            f"ForegroundActive={dec(selection_text)}",
            f"ForegroundInactive={dec(selection_text)}",
            f"ForegroundLink={dec(selection_text)}",
            f"ForegroundNegative={dec(k['negative'])}",
            f"ForegroundNeutral={dec(k['neutral'])}",
            f"ForegroundNormal={dec(selection_text)}",
            f"ForegroundPositive={dec(k['positive'])}",
            f"ForegroundVisited={dec(selection_text)}",
        ])

    groups = [
        ("[Colors:Button]", group(k["chrome"], k["window"])),
        ("[Colors:Complementary]", group(k["chrome"], k["deep"])),
        ("[Colors:Header]", group(k["chrome"], k["window"])),
        ("[Colors:Header][Inactive]", group(k["headerInactiveBackground"], k["headerInactiveAlternate"],
                                            text=k["headerInactiveText"], inactive=k["headerInactiveTextInactive"])),
        ("[Colors:Selection]", selection_group()),
        ("[Colors:Tooltip]", group(k["deep"], k["chrome"])),
        ("[Colors:View]", group(k["window"], k["chrome"])),
        ("[Colors:Window]", group(k["window"], k["chrome"])),
    ]

    wm = "\n".join([
        f"activeBackground={dec(k['wmActiveBackground'])}",
        f"activeBlend={dec(k['wmActiveBlend'])}",
        f"activeForeground={dec(k['wmActiveForeground'])}",
        f"inactiveBackground={dec(k['wmInactiveBackground'])}",
        f"inactiveBlend={dec(k['wmInactiveBlend'])}",
        f"inactiveForeground={dec(k['wmInactiveForeground'])}",
    ])

    lines = [f"[General]\nName={p['name']}\nColorScheme={p['name']}\nshadeSortColumn=false", ""]
    lines += [f"[KDE]\ncontrast={k.get('contrast', 4)}", ""]
    for title, body in groups:
        lines += [title, body, ""]
    lines += ["[WM]", wm, ""]
    text = "\n".join(lines) + "\n" + COLOR_EFFECT_DISABLED + "\n" + COLOR_EFFECT_INACTIVE

    out = EXPORTS / "kde" / f"{p['name']}.colors"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


# ---------- Kvantum ----------

def emit_kvantum(palette):
    p = palette
    ref = p["_by_name"]
    k = p["kvantum"]
    src = Path(k["baseTheme"]).expanduser()
    color_map = {rgb.lstrip("#").lower(): target for rgb, target in k["colorMap"].items()}

    def recolor(match):
        rgb, alpha = match.group(1).lower(), match.group(2) or ""
        target = color_map.get(rgb)
        if target is None:
            return match.group(0)
        return "#" + ref[target].lstrip("#") + alpha

    text = re.sub(r"#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", recolor, src.read_text())

    named = {name.lower(): "#" + ref[target].lstrip("#")
             for name, target in k.get("namedColorMap", {}).items()}

    def recolor_named(match):
        return named.get(match.group(1).lower(), match.group(0))
    text = re.sub(r"(?<=color=)([a-zA-Z]+)\b", recolor_named, text)

    out_dir = EXPORTS / "kvantum" / p["name"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{p['name']}.kvconfig"
    out.write_text(text)

    svg = src.parent / (src.stem + ".svg")
    if svg.exists():
        svg_map = {rgb.lower(): "#" + ref[target].lstrip("#") for rgb, target in k.get("svgColorMap", {}).items()}

        def sub(match):
            return svg_map.get(match.group(0).lower(), match.group(0))
        svg_text = re.sub(r"#[0-9a-fA-F]{6}", sub, svg.read_text())
        (out_dir / f"{p['name']}.svg").write_text(svg_text)
    return out


# ---------- Plasma theme ----------

def emit_plasma_theme(palette):
    p = palette
    ref = p["_by_name"]
    k = p["plasmaTheme"]
    src = Path(k["baseTheme"]).expanduser()
    svg_map = {rgb.lower(): "#" + ref[target].lstrip("#") for rgb, target in k["svgColorMap"].items()}
    file_maps = {rel: {rgb.lower(): "#" + ref[target].lstrip("#") for rgb, target in m.items()}
                 for rel, m in k.get("svgFileColorMap", {}).items()}
    token_maps = {rel: {tok: "#" + ref[target].lstrip("#") for tok, target in m.items()}
                  for rel, m in k.get("svgFileRecolor", {}).items()}
    scrim = k.get("panelScrim") or {}
    scrim_files = set(scrim.get("files", []))
    scrim_from = scrim.get("from", "")
    scrim_to = f"fill:{ref[scrim['color']]};opacity:{scrim.get('opacity', 1)}" if scrim else ""

    def apply_scrim(text, rel):
        if rel in scrim_files and scrim_from and scrim_from in text:
            return text.replace(scrim_from, scrim_to)
        return text

    def recolor(text, extra=None):
        merged = svg_map | (extra or {})

        def sub(match):
            return merged.get(match.group(0).lower(), match.group(0))
        return re.sub(r"#[0-9a-fA-F]{6}", sub, text)

    out_dir = EXPORTS / "plasma" / p["name"]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for src_file in sorted(src.rglob("*")):
        if src_file.is_dir():
            continue
        rel = src_file.relative_to(src)
        if rel.name in k["dropFiles"]:
            continue
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src_file.suffix == ".svgz":
            text = gzip.decompress(src_file.read_bytes()).decode("utf-8")
            text = recolor(text, file_maps.get(rel.as_posix()))
            for tok, col in token_maps.get(rel.as_posix(), {}).items():
                text = text.replace(tok, col)
            text = apply_scrim(text, rel.as_posix())
            dst.write_bytes(gzip.compress(text.encode("utf-8")))
        elif src_file.suffix == ".svg":
            text = recolor(src_file.read_text(), file_maps.get(rel.as_posix()))
            text = apply_scrim(text, rel.as_posix())
            dst.write_text(text)
        elif src_file.name == "metadata.desktop":
            text = re.sub(r"^Name=.*$", f"Name={p['name']}", src_file.read_text(), flags=re.M)
            text = re.sub(r"^X-KDE-PluginInfo-Name=.*$", f"X-KDE-PluginInfo-Name={p['name']}", text, flags=re.M)
            text = re.sub(r"\[Wallpaper\]\n(?:default\w+=.*\n?)*", "", text)
            dst.write_text(text)
        else:
            shutil.copy(src_file, dst)

    meta = {
        "KPlugin": {
            "Authors": [{"Email": "vinceliuice@hotmail.com", "Name": "Vinceliuice"}],
            "EnabledByDefault": True,
            "Id": p["name"],
            "License": "LGPL",
            "Name": p["name"],
            "Version": json.loads((ROOT / "package.json").read_text())["version"],
        },
        "X-Plasma-API": "5.0",
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=4) + "\n")
    return out_dir


# ---------- opencode ----------

def emit_opencode(palette):
    p = palette
    ref = p["_by_name"]
    oc = p["opencode"]

    defs = {name: ref[pal] for name, pal in oc["defs"].items()}
    theme = {}
    for key, value in oc["theme"].items():
        theme[key] = defs[value] if value in defs else (ref[value] if value in ref else value)

    doc = {
        "$schema": "https://opencode.ai/theme.json",
        "defs": defs,
        "theme": theme,
    }
    out = EXPORTS / "opencode" / "magnolia.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent="\t") + "\n")
    return out


# ---------- Mailspring ----------

def emit_mailspring(palette):
    p = palette
    ref = p["_by_name"]
    k = p["mailspring"]

    def c(name):
        return "#" + ref[name].lstrip("#")

    less = f"""@import 'base/ui-variables';

@gray-base: #ffffff;
@gray-darker: darken(@gray-base, 13.5%);
@gray-dark: darken(@gray-base, 20%);
@gray: darken(@gray-base, 33.5%);
@gray-light: darken(@gray-base, 46.7%);
@gray-lighter: darken(@gray-base, 92.5%);
@white: {c(k['deep'])};

@accent-primary: {c(k['accent'])};
@background-primary: {c(k['backgroundPrimary'])};
@background-off-primary: {c(k['backgroundPrimary'])};
@background-secondary: {c(k['backgroundSecondary'])};
@background-tertiary: {c(k['backgroundTertiary'])};

@border-color-primary: lighten(@background-primary, 10%);
@border-color-secondary: lighten(@background-secondary, 10%);
@border-color-tertiary: lighten(@background-tertiary, 10%);
@border-color-divider: @border-color-secondary;

@text-color: {c(k['text'])};
@text-color-subtle: fadeout(@text-color, 20%);
@text-color-very-subtle: fadeout(@text-color, 40%);
@text-color-inverse: {c(k['textInverse'])};
@text-color-inverse-subtle: fadeout(@text-color-inverse, 20%);
@text-color-inverse-very-subtle: fadeout(@text-color-inverse, 50%);
@text-color-heading: {c(k['text'])};
@component-active-bg: @text-color;

@text-color-link: @accent-primary;
@text-color-link-hover: @accent-primary-dark;
@text-color-link-active: @accent-primary-dark;

@btn-default-bg-color: lighten(@background-primary, 5%);
@btn-border-color: fadeout(@text-color, 65%);
@dropdown-default-bg-color: {c(k['backgroundSecondary'])};

@input-bg: {c(k['backgroundSecondary'])};
@input-border: @border-color-divider;

@list-bg: {c(k['backgroundSecondary'])};
@list-border: {c(k['backgroundTertiary'])};
@list-selected-color: @text-color-inverse;
@list-focused-color: @text-color;

@toolbar-background-color: {c(k['backgroundPrimary'])};
@panel-background-color: {c(k['backgroundPrimary'])};

.thread-icon:not(.thread-icon-unread):not(.thread-icon-star) {{
  filter: invert(100%);
}}
img.content-dark {{
  filter: invert(100%);
}}
img.content-light {{
  filter: invert(100%);
}}

.mail-label {{
  filter: contrast(110%) brightness(85%);
}}

.thread-list .list-item:not(.unread):not(.selected):not(.focused) {{
  color: {c(k['textMuted'])};
}}

.sheet-toolbar {{
  box-shadow: none;
  border-bottom: none;
}}
.sheet-toolbar-container {{
  background: @panel-background-color;
}}
body.is-blurred .sheet-toolbar-container {{
  background: {c(k['deep'])};
}}
"""
    pkg = {
        "name": "ui-magnolia",
        "displayName": "Magnolia",
        "theme": "ui",
        "version": json.loads((ROOT / "package.json").read_text())["version"],
        "description": "Magnolia dark theme for Mailspring",
        "license": "GPL-3.0",
        "engines": {"mailspring": "*"},
        "private": True,
    }
    out_dir = EXPORTS / "mailspring" / pkg["name"]
    (out_dir / "styles").mkdir(parents=True, exist_ok=True)
    (out_dir / "package.json").write_text(json.dumps(pkg, indent=2) + "\n")
    (out_dir / "styles" / "ui-variables.less").write_text(less)
    return out_dir


# ---------- GTK theme ----------

def recolor_png(data, png_map):
    """Remap exact RGB values in a non-interlaced 8-bit PNG (colortype 2/6).

    Returns None when the format is not supported; the caller keeps the file as-is.
    """
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, width, height, ct, depth, interlace = 8, b"", 0, 0, 0, 0, 0
    chunks = []
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, depth, ct = int.from_bytes(body[0:4], "big"), int.from_bytes(body[4:8], "big"), body[8], body[9]
            interlace = body[12]
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
        chunks.append((ctype, body))
        pos += 12 + length
    if depth != 8 or ct not in (2, 6) or interlace != 0 or not idat:
        return None
    channels = 3 if ct == 2 else 4
    raw = bytearray(zlib.decompress(idat))
    stride = width * channels
    if len(raw) < height * (stride + 1):
        return None

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        return a if pa <= pb and pa <= pc else (b if pb <= pc else c)

    prev = bytearray(stride)
    decoded = []
    for y in range(height):
        off = y * (stride + 1)
        ftype, cur = raw[off], bytearray(raw[off + 1:off + 1 + stride])
        for x in range(stride):
            a = cur[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if ftype == 1:
                cur[x] = (cur[x] + a) & 0xFF
            elif ftype == 2:
                cur[x] = (cur[x] + b) & 0xFF
            elif ftype == 3:
                cur[x] = (cur[x] + (a + b) // 2) & 0xFF
            elif ftype == 4:
                cur[x] = (cur[x] + paeth(a, b, c)) & 0xFF
        decoded.append(cur)
        prev = cur
    rows = []
    for cur in decoded:
        for x in range(0, stride, channels):
            mapped = png_map.get(tuple(cur[x:x + 3]))
            if mapped:
                cur[x:x + 3] = bytes(mapped)
        rows.append(b"\x00" + bytes(cur))
    body = zlib.compress(b"".join(rows), 9)

    def chunk(ctype, payload):
        return len(payload).to_bytes(4, "big") + ctype + payload + zlib.crc32(ctype + payload).to_bytes(4, "big")

    out = [data[:8]]
    for ctype, payload in chunks:
        if ctype == b"IDAT":
            continue
        if ctype == b"IEND":
            continue
        out.append(chunk(ctype, payload))
    out.append(chunk(b"IDAT", body))
    out.append(chunk(b"IEND", b""))
    return b"".join(out)


def emit_gtk_theme(palette):
    p = palette
    ref = p["_by_name"]
    k = p["gtkTheme"]
    src = Path(k["baseTheme"]).expanduser()
    css_map = {rgb.lower(): "#" + ref[target].lstrip("#") for rgb, target in k["cssColorMap"].items()}
    def rgb_tuple(rgb):
        return tuple(int(rgb.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    png_map = {rgb_tuple(rgb): rgb_tuple(ref[target]) for rgb, target in k["cssColorMap"].items()}
    png_map.update({rgb_tuple(rgb): rgb_tuple(ref[target]) for rgb, target in k.get("pngColorMap", {}).items()})

    def recolor(text):
        def sub(match):
            return css_map.get(match.group(0).lower(), match.group(0))
        text = re.sub(r"#([0-9a-fA-F]{6})\b", sub, text)
        if k.get("accentColor"):
            text = re.sub(r"(@define-color accent_color )#[0-9a-fA-F]{6};",
                          lambda m: m.group(1) + "#" + ref[k["accentColor"]].lstrip("#") + ";", text)
        return text

    out_dir = EXPORTS / "gtk" / p["name"]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for src_file in sorted(src.rglob("*")):
        if src_file.is_dir():
            continue
        dst = out_dir / src_file.relative_to(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src_file.suffix == ".png":
            recolored = recolor_png(src_file.read_bytes(), png_map) if png_map else None
            if recolored is None:
                shutil.copy(src_file, dst)
            else:
                dst.write_bytes(recolored)
        elif src_file.name == "index.theme":
            text = src_file.read_text()
            text = re.sub(r"^Name=.*$", f"Name={p['name']}", text, flags=re.M)
            text = re.sub(r"^Comment=.*$", f"Comment={p['name']} GTK theme", text, flags=re.M)
            text = re.sub(r"^GtkTheme=.*$", f"GtkTheme={p['name']}", text, flags=re.M)
            text = re.sub(r"^MetacityTheme=.*$", f"MetacityTheme={p['name']}", text, flags=re.M)
            dst.write_text(text)
        elif src_file.suffix in (".css", ".svg", ".rc", ".xml", ".xpm") or src_file.name == "gtkrc":
            dst.write_text(recolor(src_file.read_text(errors="replace")))
        else:
            shutil.copy(src_file, dst)
    return out_dir


# ---------- README palette table ----------

GROUPS = [
    ("Backgrounds", ["bg.base", "bg.chrome", "bg.deep"]),
    ("Text & neutrals", ["fg", "fg.bright", "fg.bone", "fg.muted", "fg.faint", "fg.rose", "border"]),
    ("Accents", ["red", "mint", "green", "blush", "gold", "sand", "peach", "punch", "dusk", "lilac", "taupe",
                 "cream", "petal", "maroon", "sky", "azure", "periwinkle", "rosewater", "flamingo",
                 "comment", "rust"]),
]


def terminal_group(palette):
    """ANSI-only colors: referenced by the ansi mapping but not shown in other groups."""
    listed = {name for _, names in GROUPS for name in names}
    seen = []
    for key in ("normal", "bright"):
        for name in palette["ansi"][key]:
            if name not in listed and name not in seen:
                seen.append(name)
    return ("Terminal (ANSI only)", seen)


def emit_readme(palette):
    p = palette
    ref = p["_by_name"]
    rows = ["| Color | Hex | Role |", "| --- | --- | --- |"]
    for title, names in list(GROUPS) + [terminal_group(p)]:
        rows.append(f"| **{title}** | | |")
        for name in names:
            entry = p["colors"][name]
            rows.append(f"| `{name}` | `{entry['hex']}` | {entry['role']} |")

    ansi_names = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
    rows += ["", "Terminal mapping (ANSI 16, shared by the VS Code terminal, Konsole export):",
             "", "| Slot | Color | Hex |", "| --- | --- | --- |"]
    for i, slot in enumerate(ansi_names):
        for variant, key in ((str(i), "normal"), (f"{i + 8} (bright {slot})", "bright")):
            name = p["ansi"][key][i]
            rows.append(f"| {variant} | `{name}` | `{ref[name]}` |")

    table = "\n".join(rows)

    readme = README_PATH.read_text()
    pattern = re.compile(re.escape(README_START) + r".*?" + re.escape(README_END), re.S)
    replacement = f"{README_START}\n\n{table}\n\n{README_END}"
    if pattern.search(readme):
        readme = pattern.sub(lambda _: replacement, readme, count=1)
    else:
        print(f"README: markers not found, palette table NOT written (add {README_START}/{README_END})")
        return None
    README_PATH.write_text(readme)
    return README_PATH


def main():
    palette = load_palette()
    ok = lint(palette)
    konsole = emit_konsole(palette)
    kde = emit_kde(palette)
    kvantum = emit_kvantum(palette)
    plasma = emit_plasma_theme(palette)
    gtk = emit_gtk_theme(palette)
    oc = emit_opencode(palette)
    ms = emit_mailspring(palette)
    readme = emit_readme(palette)
    ok = lint_exports(palette) and ok
    print(f"WROTE: {konsole.relative_to(ROOT)}, {kde.relative_to(ROOT)}, {oc.relative_to(ROOT)}")
    print(f"WROTE: {ms.relative_to(ROOT)}")
    print(f"WROTE: {kvantum.relative_to(ROOT)}, {plasma.relative_to(ROOT)}, {gtk.relative_to(ROOT)}")
    if readme:
        print(f"WROTE: {readme.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
