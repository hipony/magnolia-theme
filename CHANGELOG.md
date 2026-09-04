# Change Log

All notable changes to the "magnolia-theme" extension will be documented in this file.

## [0.3.0] - 2026-09-05

### Added

- Palette source of truth (`palette/palette.json`) with a generator (`tools/generate.py`, `npm run generate`) that lints the VS Code theme against the palette and exports:
  - Konsole color scheme (`exports/konsole/Magnolia.colorscheme`)
  - opencode theme (`exports/opencode/magnolia.json`)
  - Palette table in the README
- The linter also enforces the terminal ANSI 16 mapping (`terminal.ansi*` ↔ `palette.ansi`), and the README documents the slot-to-color table
- Palette section in the README

### Changed

- Terminal ANSI palette reworked to match the theme's identity: dusty sage green, champagne yellow, periwinkle blue and dusty-aqua cyan replace the generic pastels; terminal hues now have dedicated palette entries instead of sharing syntax colors
- `charts.lines` now uses the identity pink (was an off-palette grey)

## [0.2.0] - 2026-09-05

### Added

- Modern workbench surfaces: merge editor (`mergeEditor.*`, `multiDiffEditor.*`), notebooks, testing views and gauges, SCM graph, comments/PR review, quick pick (`quickInput.*`, `keybindingLabel.*`), editor action list, radio buttons, welcome page, Markdown alerts
- AI surfaces: `chat.*`, inline chat (`inlineChat*`, `inlineChatDiff`, `inlineChatInput`), inline edits (`inlineEdit.*`), inline-completion ghost text (`editorGhostText.*`), Copilot minimap/overview markers
- Sticky scroll for side bar, editor, panel, terminal, output and peek views
- Missing settings-UI colors, status bar hover/offline states, terminal find/hover highlights, debugger view colors, `gitDecoration.renamedResourceForeground`
- Overview ruler markers (errors, warnings, infos, git, find, comments, brackets) and gutter secondary change colors

### Changed

- Warnings are now muted yellow (`#ebd391`) instead of off-white
- Git conflicts are now peach (`#ffce9c`) to stand out from modified files
- Terminal ANSI palette rebuilt from the theme palette: opaque dark blue-violet black (was translucent pink), pastel normals, lightened brights
- Active indent guide is now brighter than regular guides
- Inlay hints slightly brighter; type hints use the dusty-rose type color
- Several off-palette strays normalized (`tab` backgrounds, find-match, button hovers, CodeLens, GitLens graph markers)

### Fixed

- Removed dead commented-out key, duplicate TextMate scopes, and invalid JSON trailing commas; colors are now sorted and the file is consistently formatted
- Fixed a misspelled scope (`constant.charactger.entity.js.jsx`)
