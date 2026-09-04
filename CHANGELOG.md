# Change Log

All notable changes to the "magnolia-theme" extension will be documented in this file.

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
