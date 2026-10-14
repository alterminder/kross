# Frontend

React 19 + TypeScript + Vite, with React Router, `@rjsf` for the schema-driven scenario form, Recharts for the dials
chart and `marked` for knowledge notes. The production build is served by the backend from the same origin, so there is
no CORS and the session cookie just works.

## Where things are

| Path | What |
| --- | --- |
| `src/api/` | `schema.d.ts` (generated from the backend's OpenAPI), `api()` (adds the CSRF header) and the server-sent-events reader for streamed turns |
| `src/pages/` | One file per screen (routes in `src/routes.tsx`) |
| `src/features/` | Larger pieces shared by screens: the debrief coach, the CCHN debrief section, onboarding, play helpers, preparation |
| `src/trainer/` | The trainer view: chat, live console, dials chart, turn review, frozen prompt |
| `src/editor/` | The scenario editor's custom fields, sections, labels and condition rows |
| `public/covers/` | Scenario card images ([README](../../frontend/public/covers/README.md)) |
| `e2e/` | Playwright journeys against the dev server |

## Screens

| Route | Screen |
| --- | --- |
| `/` | Scenario library |
| `/scenarios/new` | Create a scenario: import a brief or use the guided builder |
| `/scenarios/:id`, `/scenarios/:id/edit` | Scenario card; the editor (form with plain-language condition rows, or raw YAML) |
| `/play/:id` | Play a session, with the counterpart's reply streamed in |
| `/sessions/:id/debrief` | The debrief: outcome, skill bars, what went well and what was missed, "Ask the Coach" |
| `/sessions/:id/watch` | The trainer view (below) |
| `/knowledge` | The knowledge library (CCHN tools and practice notes) |
| `/org`, `/rules`, `/usage` | Organisation admin, behaviour rules, usage report |
| `/invite`, `/signin`, `/privacy` | Invite acceptance, sign-in, the privacy notice (public) |

## The trainer view

`/sessions/:id/watch` shows a session as the trainer sees it:

- **Live session:** the chat, dial sliders, preset and free-text twists, rules fired, goal progress.
- **Debrief:** dials over time, turn-by-turn review with scores and comments, and the exact prompt the counterpart was
  sent.

Two ways in: **Playtest** your own scenario (the play page shows the same console and an "Open trainer view" link), or,
as an org admin, open a member's session from the Organisation page. Admins can steer (adjust dials, fire twists) and
comment; the player never sees comments. Live updates poll every two seconds.

## Build-time flags

`VITE_HIDE_PREP`: the strategic preparation (Naivasha Grid) controls are hidden unless the build sets
`VITE_HIDE_PREP=0`. It is read at compile time, so it cannot be changed at runtime.

## Development

See [development.md](../development.md) for running the dev server, tests and regenerating the API types.
