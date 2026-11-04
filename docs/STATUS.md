# Completion status

This status distinguishes working desktop implementation from native preparation and external integration dependencies.

| Area | Status |
| --- | --- |
| Project creation, switching, naming and persistence | Implemented; SQLite + revisions |
| Project delete / restore | Web confirmation + local trash, retained media/exports/history; active exports block deletion |
| Selected permanent deletion | Per-row and checkbox selection, explicit target confirmation, subset revision checks; other trash remains recoverable |
| Empty project trash | Explicit permanent-delete confirmation, exact-set revision check, media/history/job cleanup, durable pending-file retry and startup recovery; synthetic API tests |
| Round / Shot / Design UNDO / REDO / RESET | Web controls + revision-checked shared API; persisted 100-step field deltas per section, reset confirmation, dependency/collision checks |
| MP4/MOV/WebM upload and metadata | Implemented; browser codecs vary |
| Native HTML video, seek, frame steps, timeline zoom | Implemented |
| Round, 18-hole par/yardage/score editing | Implemented; unknown values retained |
| Front/back/overall/relative scoring and score indicators | Implemented; partial-hole totals labeled |
| Shot CRUD, per-hole numbering and list reordering | Implemented |
| Timed shot/card events, timeline dragging and validation | Implemented |
| Overlay templates, colors, typography, transparency, presets | Implemented |
| Preview drag/resize and portrait coordinates | Implemented |
| Shared PNG preview/export rendering | Implemented and pixel-compared in synthetic export test |
| Actual FFmpeg MP4/H.264/AAC export + progress/download | Implemented and tested with synthetic audio/video |
| Course library search, multi-tee/category selection | Saved local library plus explicit GolfCourseAPI online name search/import |
| GolfCourseAPI key settings and imports | Implemented; local secret settings, 24-hour cache, exact tee/category/hole mapping; live user-key validation pending |
| Manual shot numbers and popup themes/transparency | Broadcast name/prior-hole-score/hole/yardage/large-shot popup, large remaining distance + club/total strip, enlarged labels, six themes and shared preview/export |
| Immutable scorecard timeline snapshots | Shared model/rendering; 5/9/18-hole captures, confirmed replacement/history and real three-card MP4 pixel tests; web confirmation/immutable-data/replacement/history QA verified; native device testing pending |
| Modern 18-hole scorecard | Two nine-hole sections; actual digit ink centered within single/double circle/square indicators |
| Default overlay layouts | Requested shot/card coordinates, font 30 and radius 20; web/native creation + undoable Design RESET; saved styles retained |
| Aspect-aware layout presets | Explicit layout fitting respects the source aspect; explicit recommended-layout action preserves old projects until selected |
| Source snapshots and round override detection | Implemented |
| Authorized JSON/CSV import and reference image/PDF upload | Implemented; no OCR |
| Live USGA search/API | Not implemented: permission/provider integration required |
| Multi-player comparison, multi-video assembly, audio waveform | Not implemented |
| Native Expo source and generated API client types | Prepared; TypeScript and JS bundle verification recorded in handoff |
| Native local course/round/shot/video/export screens | Source implemented; device testing pending |
| Native SQLite cache/outbox/revision conflict handling | Source implemented; device/offline interaction testing pending |
| Native gesture overlay designer / complete timeline editor | Not implemented; use web editor |
| Native iOS/Android compiled development builds | Not produced in this task |
| Physical iPhone connectivity to a hosted API | Not configured; current API is loopback only |
| Cloud auth/ownership, SecureStore, HTTPS/object storage | Not implemented |
| Resumable/background upload and push notifications | Not implemented |
| App signing, EAS registration, App Store/Google Play release | Not performed |

## Verification evidence

- Backend suite: 122 tests, including a real FFmpeg export of synthetic video with audio, RGBA panel equality, timeline boundaries, portrait proportions, course reference immutability and optimistic-write conflicts.
- Existing adjacent ShotTracer suite: 92 tests passed; source was not edited.
- Browser QA uses a temporary data home: Korean workspace render, real keyboard round entry/autosave, synthetic video upload, shot creation, preview graphics and real export submission/download readiness.
- GolfCourseAPI integration tests use synthetic responses; no real API key was supplied. Credential redaction, auth/rate-limit/network errors, caching, refresh and snapshot integrity are covered.
- JavaScript suite: 11 tests for manual numbering, theme preservation, portrait/landscape recommended layouts, score classes and requested default geometry/typography.
- Raster tests verify digit/marker centers across sans/serif/mono, including two-digit scores and dashes. The real export test overlays the broadcast shot and modern full card together with audio.
- Snapshot web QA: a temporary synthetic-video project captured 5 holes, entered Hole 6 without altering the old 20-stroke card, confirmed replacement to a 24-stroke v2, and inspected retained v1 history.
- Native snapshot actions share the revision-checked server APIs; TypeScript, official dependency validation and iOS/Android JS exports passed. No simulator or physical-device acceptance is claimed.
- Project history/trash web QA: edited and undid/redid round data, confirmed and undid round reset, undid a shot club change and a card theme change, reset design, deleted/restored the synthetic-video project and verified retained graphics/history controls.
- Empty-trash browser QA: isolated temporary projects verified the enabled button, exact project name/count, irreversible-delete warning and Cancel path; permanent removal/failure/restart checks ran only against pytest scratch data.
- Selected-trash/prior-hole-score QA: checkbox and row actions confirmed only one named temporary target; Cancel preserved both trash items. A Hole 3 popup displayed -1 from Holes 1–2 despite entered current/future scores. The synthetic MP4 test uses the same prior-hole scoring path.
- Default-layout browser QA: new shot fields matched (.75,.03,.2,.15), new card fields matched (.24,.2,.504,.56), both font 30/radius 20, and both panels appeared without collision on the same synthetic frame.
- Approved broadcast distance swap: remaining yards occupy the primary cell; club and total yards occupy the lower strip. Raster tests cover enlarged label placement and ink bounds across three fonts at sizes 12/30/48; actual MP4 composition still matches the shared panel.
- Timeline zoom QA: measured ruler/seek/playhead/shot/popup/card coordinates at 2×/4×/8× with scroll; row starts matched exactly and ruler interpolation differed by less than 0.01 px. At 8×, seeking at the 6-second point reached 6.001 s; a 68 px shot drag moved both shot and popup by 0.24927 s and UNDO restored 5–10 s. Added six numeric axis/scroll/anchor/tick regression tests.
- Source and mobile lockfiles are retained for reproducibility. See README commands for rerunning validation.

## Next development milestones

1. Run the development client on iOS simulator and Android emulator; exercise offline changes, reconnect, cross-client conflicts and native video upload/playback.
2. Add native touch timing/design, mobile translations, conflict merge/export UX and gallery/share integration.
3. Validate GolfCourseAPI with a user-provided key and representative live courses; add any separately authorized USGA integration only with appropriate access.
4. Design hosted authentication/authorization/storage/render infrastructure before exposing a shared production endpoint.
5. Build signed device artifacts, verify background behavior and store privacy declarations, then prepare store submissions with owner-provided accounts.
