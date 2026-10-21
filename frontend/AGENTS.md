# AGENTS.md — frontend

Applies to everything under `frontend/`. The root `AGENTS.md` still applies in full; this file adds frontend-specific rules.

## Tech stack

Versions are pinned in `package.json`. Check them before relying on version-specific behaviour, and look up docs for those exact versions.

| Concern | Choice |
|---|---|
| Language | JavaScript (ES modules), no TypeScript |
| Framework | Vue 3.4, Composition API with `<script setup>` only |
| Build and dev server | Vite 5.4 with `@vitejs/plugin-vue` |
| State | Pinia 2.2 |
| Routing | Vue Router 4.4 |
| Styling | Tailwind CSS 3.4 (PostCSS and Autoprefixer), with the Bauhaus design tokens in `tailwind.config.js` |
| Data | FastAPI backend through `src/services/api.js`. `@supabase/supabase-js` 2.45 is installed but is not used for data access. |
| Tests | Vitest 3.2 with jsdom (`npm test`) |

## Layout

```
frontend/src/
  assets/main.css         Tailwind layers, base canvas/ink colours, .active-press utility
  components/common/      Bauhaus* design-system components (shared by every screen)
  components/<domain>/    domain components, e.g. venues/VenueCriteriaForm.vue
  features/<domain>/      everything for one domain except components/views: Pinia stores and pure logic,
                          e.g. events/dashboard.js, events/store.js
  stores/                 app-wide stores only (auth.js)
  services/api.js         the only place HTTP calls are made (authApi, venuesApi, eventsApi)
  router/index.js         routes and guards (meta.requiresAuth, meta.allowedRoles)
  views/                  route-level pages; views/dashboards/ has one dashboard per role
  **/__tests__/           Vitest specs, next to the code they test
```

### Where stores go

This is a team decision, following `docs/archive/2026-09-13-design-review.md` A3 #8 ("restructure the frontend around features").

- **Domain stores go in `features/<domain>/`** (events, venues, equipment, registrations, notifications), next to that domain's pure logic. A store that belongs to one domain never goes in `stores/`.
- **When a domain has more than one store**, give each file the store's name (e.g. `features/events/coordinatorDashboardStore.js`, `features/events/eventRequestStore.js`) instead of adding a second `store.js`.
- **Before creating a store, check the domain's folder** for one you can extend. Two stores must not fetch or cache the same data.
- **`stores/` is only for app-wide state** used across domains, which today means `auth.js` — and only `auth.js`. Every domain store now lives under `features/`; SCRUM-70 moved the last straggler (`stores/venues.js` → `features/venues/venueSearchStore.js`).

## Design system: keep every screen aligned

Treat this as the design brief for **any** UI work, whether a new view, a dashboard widget, or a form:

> Build this in ConnectSphere's **Bauhaus constructivist** style. Use a white canvas and black ink, with primary red, blue, and yellow reserved for meaning and emphasis. Use thick black borders, hard offset shadows with no blur, and only square or perfectly round shapes. Typography is bold, geometric, and uppercase. Compose the screen from the existing `Bauhaus*` components, and don't introduce new colours, fonts, radii, or shadows. It must work on mobile and desktop, and should look like it belongs next to the venue search and coordinator dashboard screens.

**Tokens.** Use the Tailwind names, never raw hex values.

| Token | Value | Where it's used today |
|---|---|---|
| `canvas` | `#FFFFFF` | page background; text on red/blue buttons |
| `ink` | `#121212` | text, borders, hard shadows |
| `bauhaus-red` | `#D02020` | `BauhausButton variant="primary"` |
| `bauhaus-blue` | `#1040C0` | `BauhausButton variant="secondary"` |
| `bauhaus-yellow` | `#F0C020` | `BauhausButton variant="yellow"`, text selection |
| `bauhaus-green` | `#2E7D32` | the `ACTIVE` status badge on the venue-staff dashboard's venue rows — the one status that needs no attention. Not a Bauhaus primary; don't spend it on anything else without saying why |
| `muted` | `#E0E0E0` | nav link hover (every at-rest surface is white — don't fill panels with it) |
| `font-sans` | Outfit 400/500/700/900 | all text |
| `shadow-hard` / `shadow-hard-lg` | 4px / 8px offset, no blur | cards and raised elements |

Colours carry meaning through the components. Use a component's variant (e.g. `variant="primary"`) instead of applying a primary colour by hand, so the same action looks the same on every screen.

**Rules**

- **Components first.** Before writing markup, check `components/common/`: `BauhausButton`, `BauhausCard`, `BauhausInput`, `BauhausSelect`, `BauhausCheckboxGroup`, `BauhausEmptyState`, `BauhausNavbar`. If one is close, add a prop or slot rather than creating a look-alike.
- **Shape.** Use `rounded-none` or `rounded-full` only, and borders in `border-ink` (`border-2` or `border-4`, matching the existing components).
- **Type.** Headlines use `uppercase font-black tracking-tighter leading-[0.9]`. Labels use `font-bold uppercase tracking-widest`.
- **Interaction.** Pressable elements use `.active-press` so they press flat on click.
- **No new visual values inline.** If a colour, shadow, or size is genuinely missing, add it to `tailwind.config.js` and tell the developer. Don't use an arbitrary `bg-[#…]`.
- **Static class names only.** Never build a class like `` `bg-${color}` ``, because Tailwind's scanner won't see it. Use a lookup object of full class names, as `BauhausCard.vue` does.
- **Empty states, not fake data.** When a widget's data doesn't exist yet, render `BauhausEmptyState` (`docs/REQUIREMENTS.md` §6.21).
- **Labels and field rules** come from `docs/REQUIREMENTS.md` §6. Event status labels already exist in `features/events/dashboard.js`, so reuse them.
- **Summary cards stay aligned when text wraps.** Reuse `BauhausSummaryCard` for dashboard metric tiles. Cards in the same row must have equal outer heights and aligned figures/descriptions. Reserve at least two lines for labels and details with minimum heights, let longer content grow, and never truncate text or use rigid fixed card heights to hide wrapping. A card inside a link or other grid wrapper must stretch to fill that wrapper. Choose column breakpoints using the content space left beside the sidebar: current summary rows use one column by default, two at `md`, and three or four at `xl`. Verify long labels, wrapped descriptions, phone widths and desktop breakpoint boundaries in a real browser; hover/focus cues must not change the card height.
- **Page padding.** Every page's root is `<main class="py-12">` and nothing more. The side gutters come from `App.vue` (`pl-4 pr-6 sm:pl-8 sm:pr-10`), so a page that adds its own `px-*`, `mx-auto` or `max-w-*` ends up narrower and more indented than the rest of the app. Non-padding classes such as `break-words` are fine. `src/views/__tests__/pagePadding.spec.js` fails any view that breaks this. Inside a page, follow the venue detail page's rhythm: cards use `BauhausCard`'s own padding, a card heading sits `mb-4` (or `mt-4`) from its content, a label sits `mt-2` above its value, and fields are `gap-4` apart.
- **Mobile-first.** Start from the narrow layout and add `sm:`/`md:`/`lg:` breakpoints.
- **Verify visually.** Run the dev server, open the screen as an allowed role and as a disallowed role, take a screenshot, compare it with an existing screen, and check the console for errors.

## Conventions

- **Talk only to the FastAPI API**, through `services/api.js`. Add new calls to the domain's object there (e.g. `eventsApi`). Don't use the Supabase JS client for data or business actions. Only `VITE_`-prefixed publishable values may reach the browser.
- **Route guards and `v-if` role checks are UX, not security.** The API enforces every permission.
- **Session handling** lives in `stores/auth.js` and `services/api.js`. Reuse their token and refresh handling, and never attach tokens or handle `401` inside a view.
- Register components by importing them where they're used. Don't register them app-wide with `app.component()` unless the developer asks.

## Reuse

- **UI used by two or more screens, or likely needed by another role's dashboard,** becomes a component: in `components/common/` if it's a design-system piece, or `components/<domain>/` if it's domain-specific.
- **Pure logic** (formatting, grouping, sorting, status mapping, date/time conversion) goes in plain exported functions under `features/<domain>/`, with Vitest specs. `features/events/dashboard.js` is the model. Also reusable: `features/venues/singaporeTime.js` (`singaporeDayKey`, `toSingaporeIso`, `startOfSingaporeDayUtc` — the fixed +08:00 arithmetic every screen needs to decide *which day* something falls on), `features/venues/calendar.js` (month-grid construction) and `features/venues/venueSearchStore.js` (`criteriaToParams`).
- **Stateful logic shared across components** becomes a composable (`use<Thing>`) or a Pinia store, not copy-pasted `ref`s.
- **Keep views thin.** A view wires a store, components, and routing, and shouldn't hold logic another screen would need.
- Before adding anything, check the frontend section of `docs/IMPLEMENTATION_MAP.md`.

## Tests

- Run `npm test` (Vitest) from `frontend/`.
- Unit-test pure functions and store actions (mock `services/api.js`). Put specs in a `__tests__/` folder next to the code.
- A green test run and a clean `npm run build` are not UI verification. Check the screen in a browser as described above.
