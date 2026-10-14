# Scenario card covers

One background image per cover theme (`nlab.api.content.Cover`). The frontend shows `/covers/<theme>.webp` behind a
scenario card's title; the lower third of each image is kept calm for the text.

| Theme | Used by |
| --- | --- |
| `field` | default for new scenarios |
| `camp` | Access to an IDP camp |
| `checkpoint` | Hostile checkpoint commander |
| `detention` | Detained before nightfall |
| `border` | The no man's land |
| `school` | Restoring a school occupied by armed actors |
| `hospital`, `convoy`, `office` | available to authors |

Generated on 2026-09-30 with Google `gemini-3-pro-image` (16:9, resized to at most 1600×900, WebP quality 80) by
`scripts/generate_covers.py`; the shared style prompt lives in `nlab/api/pictures.py` (one copy, shared with the app's
painter), and the script holds one scene description per theme. The prompt
rules out text, logos, flags, insignia, weapons aimed at anyone, identifiable people and the red cross, red crescent
or any other humanitarian emblem, whose use is protected by law. Check a new image for all of these before committing
it; `school` and `office` needed a second attempt because the first ones split into two unrelated scenes.
