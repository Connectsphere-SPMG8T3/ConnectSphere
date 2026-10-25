# 23-R verification — independent headless checks and PR screenshots — 2026-10-25 SGT

| | |
|---|---|
| Commit | `c2aeefc` before documentation/screenshots on `feature/scrum-23-r-equipment-availability` |
| Browser | Headless Chromium 153.0.8010.12; Asia/Singapore; en-SG |
| Viewports | 1280×900, 768×900, 375×900 |
| Environment | Branch servers localhost:5179/8013; real shared Supabase; retained user-requested DEMO fixtures; no API responses stubbed |
| Run by | Codex automated browser checks, separate from the developer manual pass |
| Result | 20 assertions passed; 10 screenshots captured; 0 console/page errors |

| Check | Result |
|---|---|
| Inventory Projector: total 7, reserved 0, maintenance 2, available 5, UNDER REPAIR | Pass |
| Inventory Microphone: total 4, reserved 0, maintenance 4, available 0, OUT OF STOCK | Pass |
| Inventory Speaker: total 3, reserved 0, maintenance 0, available 3, AVAILABLE | Pass |
| Inventory desktop: no document overflow (1280/1280) | Pass |
| Projector 2026-10-26T10:00–2026-10-26T12:00: needed 6, available 5, missing 1, Insufficient, DEMO Store A | Pass |
| Availability desktop: no document overflow (1280/1280) | Pass |
| Projector 2026-10-26T10:00–2026-10-26T12:00: needed 5, available 5, missing 0, Sufficient, DEMO Store A | Pass |
| Microphone 2026-10-26T10:00–2026-10-26T12:00: needed 1, available 0, missing 1, Insufficient, Not recorded | Pass |
| Speaker 2026-10-26T10:00–2026-10-26T12:00: needed 3, available 3, missing 0, Sufficient, DEMO Store B | Pass |
| Speaker 2026-10-26T09:00–2026-10-26T10:00: needed 3, available 0, missing 3, Insufficient, DEMO Store B | Pass |
| Speaker 2026-10-26T10:00–2026-10-26T12:00: needed 3, available 3, missing 0, Sufficient, DEMO Store B | Pass |
| Touching outage boundaries do not reduce middle-window stock | Pass |
| Projector 2026-10-29T10:00–2026-10-29T12:00: needed 6, available 7, missing 0, Sufficient, DEMO Store A | Pass |
| Projector 2026-10-26T10:00–2026-10-26T12:00: needed 6, available 5, missing 1, Insufficient, DEMO Store A | Pass |
| Availability 768px: no document overflow (768/768) | Pass |
| Projector 2026-10-26T10:00–2026-10-26T12:00: needed 6, available 5, missing 1, Insufficient, DEMO Store A | Pass |
| Availability 375px: no document overflow (375/375) | Pass |
| Duplicate rows: guidance displayed, no availability request, stale results cleared | Pass |
| Duplicate validation tablet: no document overflow (768/768) | Pass |
| No console errors or uncaught page errors | Pass |

[Screenshot gallery](../screenshots/23r-2026-10-25/README.md). Captured actual page/element screenshots only, without tokens, headers, localStorage or browser developer tools. Desktop/tablet/phone screenshots were visually inspected by Codex; that does not replace the separately reported developer manual judgement.

The screenshot script initially used an exact label match that did not match the native selector’s accessible label; corrected the capture locator to match the existing working E2E locator before completing this run. No product change was made.

Separate finding D61: the pre-existing maintenance-card formatter hardcodes UTC without a zone label. With the browser in Asia/Singapore it renders the demo start 25 Oct00:00 SGT as24 Oct16:00. Inventory-window fields and availability results tested here remain correct. This was logged rather than silently changing another story.
