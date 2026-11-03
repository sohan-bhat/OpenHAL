# Shared design assets

`tokens.css` holds the colors, type, spacing, syntax theme and motion tokens of the protocol theme in docs/DESIGN.md. The website, the Inspector and the README image tools all use it. Change docs/DESIGN.md first, then this file.

`fonts/` holds IBM Plex Sans and IBM Plex Mono as WOFF2 files subset to Latin, with their SIL Open Font License texts. The files come from the Fontsource packages `@fontsource-variable/ibm-plex-sans` 5.3.0 and `@fontsource/ibm-plex-mono` 5.3.0. Plex Sans is variable, so one file covers every weight. Plex Mono ships one file per weight, so only the weights in use are kept.

| Face | Files | License |
|---|---|---|
| IBM Plex Sans | ibm-plex-sans-latin-wght-normal.woff2 and the italic, weights 100 to 700 | OFL-1.1, OFL-ibm-plex-sans.txt |
| IBM Plex Mono | ibm-plex-mono-latin-400-normal.woff2, the 600 and 700 normal files and the 400 italic | OFL-1.1, OFL-ibm-plex-mono.txt |
