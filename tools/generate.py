#!/usr/bin/env python3
"""Magnolia theme generator.

- Lints the VS Code theme against palette/palette.json (no stray colors)
- Emits Konsole .colorscheme, KDE .colors, and opencode theme into exports/
- Regenerates the palette table in README.md

Zero dependencies, Python 3.8+. Run: python3 tools/generate.py
"""
import json
import re
import sys
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
    hover = k["accentHover"]
    selection = k["selectionBackground"]
    selection_alt = k["selectionAlternateBackground"]
    selection_text = k["selectionText"]

    def group(background, alternate):
        return "\n".join([
            f"BackgroundAlternate={dec(alternate)}",
            f"BackgroundNormal={dec(background)}",
            f"DecorationFocus={dec(accent)}",
            f"DecorationHover={dec(hover)}",
            f"ForegroundActive={dec(accent)}",
            f"ForegroundInactive={dec(k['textInactive'])}",
            f"ForegroundLink={dec(k['link'])}",
            f"ForegroundNegative={dec(k['negative'])}",
            f"ForegroundNeutral={dec(k['neutral'])}",
            f"ForegroundNormal={dec(k['text'])}",
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
            f"ForegroundInactive={dec(k['border'])}",
            f"ForegroundLink={dec(selection_text)}",
            f"ForegroundNegative={dec(k['negative'])}",
            f"ForegroundNeutral={dec(k['neutral'])}",
            f"ForegroundNormal={dec(selection_text)}",
            f"ForegroundPositive={dec(k['positive'])}",
            f"ForegroundVisited={dec(k['visited'])}",
        ])

    groups = [
        ("[Colors:Button]", group(k["chrome"], k["window"])),
        ("[Colors:Complementary]", group(k["chrome"], k["deep"])),
        ("[Colors:Header]", group(k["chrome"], k["window"])),
        ("[Colors:Selection]", selection_group()),
        ("[Colors:Tooltip]", group(k["deep"], k["chrome"])),
        ("[Colors:View]", group(k["window"], k["chrome"])),
        ("[Colors:Window]", group(k["window"], k["chrome"])),
    ]

    lines = [f"[General]\nName={p['name']}\nColorScheme={p['name']}", ""]
    for title, body in groups:
        lines += [title, body, ""]
    text = "\n".join(lines) + "\n" + COLOR_EFFECT_DISABLED + "\n" + COLOR_EFFECT_INACTIVE

    out = EXPORTS / "kde" / f"{p['name']}.colors"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


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


# ---------- README palette table ----------

GROUPS = [
    ("Backgrounds", ["bg.base", "bg.chrome", "bg.deep"]),
    ("Text & neutrals", ["fg", "fg.bright", "fg.bone", "fg.muted", "fg.faint", "fg.rose", "border"]),
    ("Accents", ["red", "mint", "green", "blush", "gold", "sand", "peach", "punch", "lilac", "taupe",
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
    oc = emit_opencode(palette)
    readme = emit_readme(palette)
    print(f"WROTE: {konsole.relative_to(ROOT)}, {kde.relative_to(ROOT)}, {oc.relative_to(ROOT)}")
    if readme:
        print(f"WROTE: {readme.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
