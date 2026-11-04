# Architecture and implementation decisions

## Repository inspection

The user-specified `scorecard/` directory was empty. The adjacent `shottracer/` project uses Python 3.13, FastAPI, Pillow/FFmpeg, plain JavaScript, file-backed projects and a separate mobile port. It has no shared hosted authentication/database service for this new editor. Existing source and the user's modified Xcode project were left untouched.

The implementation reuses that technology choice in a separate local application, rather than adding a cloud service or restructuring ShotTracer. React is used only for the new native Expo client. This preserves a buildless web editor and avoids coupling scorecard work to tracer analysis. These are independent applications; integrating tracer analysis into this editor would be a separate feature, not a completed capability.

## Boundaries

- `models`: validated golf, source-reference, video, overlay and styling data; pure scoring and timeline functions. All course values begin unknown. Scores remain optional. Half-open timeline intervals avoid two overlays at exact cuts.
- `storage`: SQLite/WAL with parameterized queries. Project JSON plus an independent revision column support compare-and-swap writes. Reusable course versions are immutable rows. Imported course snapshots in rounds are server-managed; round edits are separate overrides. Jobs persist independently.
- `graphics`: Pillow renders transparent PNG panels. Preview consumes these PNGs, and FFmpeg consumes the same panels scaled to output resolution. A single logical coordinate system respects source aspect ratio. No external fonts/assets are downloaded at runtime.
- `rendering`: ffprobe determines display dimensions, accounting for rotation. A single background worker freezes the submitted project revision, generates panels, uses half-open FFmpeg overlay expressions, encodes H.264/AAC, records actual progress and cleans scratch assets. Source and output video timing remain unretimed. Exports retain only the first audio track. Output is SDR yuv420p; HDR/color-managed editing is not promised.
- `course_api`: explicit read-only GolfCourseAPI adapter with fixed HTTPS host, no credential-forwarding redirects, local 0600 key settings/environment override, 24-hour SQLite cache, validated immutable course imports and sanitized errors.
- `api`: versioned local endpoints, bounded uploads, restricted Host/Origin and opaque server-owned source/reference paths. Video file responses support HTTP range requests. All file/SQLite work stays on the user's device.
- `web`: no framework/build requirement. A serialized save queue preserves revisions; HTML values are escaped. Native HTML video is the playback clock. Raster layers reuse export output; CSS handles placement only. Pointer gestures operate on the video rectangle, not the preview well.
- `mobile`: Expo Router root with five native workspace screens, generated OpenAPI input contracts, SQLite cache/outbox and optimistic revision sync. The server remains the scoring authority. Defaults in request schemas are optional, so the client treats persisted top-level project fields as required. Actual native runtime/device validation remains pending.

## Local versus hosted deployment

This is intentionally a loopback service. iOS simulator and Android USB/emulator port reversal can use the same local server and SQLite database. No network binding flag is provided. Host and Origin checks are defense in depth, not user authentication.

A production shared web/iOS/Android service requires a separately authorized architecture step: OIDC/session authentication and project ownership, HTTPS, object storage with scoped uploads, upload quotas/rate limits, durable render workers, credential handling, resumable uploads and push notifications. Merely changing the host to 0.0.0.0 would not implement these controls and is not the supported mobile production workflow.

## USGA integration boundary

Public NCRDB lookup is a user-opened link. The website did not establish permission for a reusable automated data feed, and the WHS programme documents controlled API participation. The app implements manual entry, authorized CSV/JSON import and the documented GolfCourseAPI search/detail endpoints. GolfCourseAPI is a separate provider and imports are not labeled USGA-verified. Only explicit configured course requests leave the backend; video/project data and API keys are never sent to unrelated hosts.

The GolfCourseAPI adapter and any future provider adapters must return tee/category-specific published values and independent provenance. Hole-level data must come from an authorized hole-level source. It must create a new local course version and require explicit round replacement; it cannot mutate an existing snapshot or infer hole yardages from aggregate length.

Research references (checked 2026-11-04):
- https://ncrdb.usga.org/courseTeeInfo.aspx
- https://www.whs.com/articles/2024/2024-interoperability.html
- https://expo.dev/changelog/sdk-56
- https://api.golfcourseapi.com/docs/api/openapi.yml (GolfCourseAPI 1.3.0; Bearer authentication, opaque 8-character IDs, summary search and tee detail schemas)

## Testing contract

Use a temporary `GVS_HOME`; never point tests or synthetic uploads at real user data. Export tests generate tiny videos in pytest scratch space and inspect codecs, audio/video alignment and overlay pixels. The web UI has been manually exercised with a separate temporary home. Native JS bundle/type checks do not establish native compile, permission, playback or offline behavior on a phone.


## Number and opacity compatibility

`Shot.number` is an optional 1–99 display override. Missing/null retains ordinal numbering within each hole; it does not alter other shots, list order or timestamps. Reordering never changes a manual override. The web and native entry UI persist this field, and `graphics.panel` uses the same server numbering helper.

`Style.overlay_opacity` defaults to 1 for old projects and presets. The web exposes the inverse percentage as whole-popup transparency. Shared panel rendering multiplies the final alpha channel, including text, accent and score indicators. Existing `Style.opacity` remains background-only alpha. Theme presets replace only three colors, leaving timing, geometry, both alpha settings and fonts intact.


## Broadcast rendering and centered score marks

The shot template reads player, relative score through holes before the shot’s current hole, hole/par/yardage and manual-or-auto shot number. The approved broadcast layout places remaining yards in the large middle cell and club/total hole yards in the lower strip. HOLE, PAR, LEFT, TO PAR and club labels/values use enlarged ink-fitted regions and honor the font-size control. The minimal template stays unchanged. `models.score_before_hole` excludes the current and all later holes regardless of saved scores or video time. Hole 1 starts at zero; missing prior score/par returns unknown rather than a partial cumulative score. Corrections to earlier holes update shot popups; immutable scorecard snapshots remain unchanged. Minimal graphics retain individual shot distance.

Full cards have two nine-hole sections; front/back cards have one. All label/data rows share nine fixed column centers. `score_symbol` uses a common center for the circle/square and the digit. `centered_text` uses cached font-mask ink bounds (including bearings), not font advance/line metrics; line-metric centering visibly shifts dashes and some digits. No raster preview/export paths diverge.

New overlay geometry uses the owner's explicit normalized defaults: shot (.75,.03,.2,.15), scorecard (.24,.2,.504,.56), font 30 and radius 20. `models.default_style` serves backend card creation and Design RESET; web creation uses matching `defaultGeometry`/`DEFAULT_TEXT_STYLE`, and native shot creation uses the same requested values. Legacy `Style` defaults are retained to avoid changing older saved/omitted fields. Existing projects keep their saved geometry and colors. The explicit recommended-layout action changes only geometry; applying colors to all graphics changes only the existing three color fields. No model migration or API contract change is required. The editable web table uses a fixed square wrapper with centered input and concentric pseudo-element marks, keeping input borders and focus rings independent.

## Immutable timeline scorecards

`ScorecardSnapshot` and its nested data are frozen Pydantic models with tuple holes. `Overlay.snapshot_id` references a project-owned capture, never the live round. Shot/minimal graphics continue using their existing live model. Capture copies all display metadata and computes completed-hole totals; unknown completed pars yield unknown relative score. `graphics.panel` reads snapshots for every full/front/back card in both PNG and MP4 paths.

Preview, insert and confirmed replacement are dedicated revision-checked API actions. Preview does not persist. Insert captures the same revision shown in confirmation, with a fresh ID. Replacement creates a new version and retains its parent; general PUT rejects snapshot mutations or card reference reassignment. Presentation edits preserve the capture's original timeline position. Projects retain orphaned history (maximum 1,000 records). A singleton round uses project ID as round identity.

Legacy cards freeze saved round data once at load/startup. Storage persists the migration with a revision+JSON compare-and-swap and increments revision so stale clients conflict. Legacy captures are labeled because actual historical insertion data is unavailable. Native insertion first syncs outbox, loads a fresh server revision, previews, then confirms through these same APIs; it never captures an offline cache silently. Physical-device checks remain pending.

## Scoped edit journal and project trash

`history.py` normalizes holes/shots/overlays by identity and stores leaf deltas in `edit_history` within the same SQLite transaction as each project revision. Batched saves partition round, shot (including dependent popup CRUD/timing), and design edits into separate histories. Undo/redo compares each affected field with the expected state before applying it to the current project, preserving unrelated changes. Missing/dependent objects or invalid restored layouts reject the whole transaction. Only the newest 100 entries per project/scope remain; new edits discard that scope's unapplied redo entries. Trusted journal replay can restore owned snapshot references while retaining all immutable capture records; general PUT still cannot mutate or reassign them.

Reset is a confirmed, journaled server action: blank manual round / imported tee defaults, remove all shot objects and their popups, or restore factory graphic styles. It never resets video, imported reference identity or captured score data. Design reset preserves template/timing/presets and validates all panel collisions before saving. Source/reference uploads, project names and provider credentials are outside the journal. Journal entries stay in SQLite and are excluded from JSON backups. Web toolbar/keyboard controls call the shared revision-checked endpoint; native UI controls remain future work.

`project_trash` is a tombstone table so existing project JSON and media paths remain intact. Active loaders/listing skip tombstones; restore removes them and increments revision. Delete/restore retain edit history, source media and renders. A SQLite writer transaction serializes export queue publication with trashing: deletion rejects queued/running jobs, and queue creation rejects a stale or trashed project. The confirmed empty-trash endpoint accepts the exact project ID/revision set displayed in the dialog and rejects changed/restored/added trash. Under the SQLite writer lock it removes project/history/job/tombstone rows and commits a durable `purge_queue` in the same transaction before touching files. Transaction failure preserves recoverable trash and all files; a crash after commit leaves an approved cleanup entry to resume. Cleanup removes only the queued project directories, skips any reused project identity, never follows symlinks, and retains failed file removals for explicit retry or startup recovery. No active projects, shared course rows or credentials are deleted. Schema additions use CREATE IF NOT EXISTS and preserve existing projects.

Selected trash deletion uses a separate nonempty-list endpoint and the same confirmation/revision/queue cleanup implementation. It checks only the selected ID/revision subset against current trash under the writer lock, so unrelated trash changes do not broaden or block the selection. Whole-trash emptying retains its exact-set check. Per-row actions and checkboxes both display the selected names/count before deletion.

## Timeline coordinate contract

The seek input lives inside the same `#tracks` element as ruler/shot/graphic rows and playhead. All use full video-duration percentages of one expanded content width. Marker padding is isolated in an absolutely positioned label; neither a 1%-duration floor nor border/min-width enlarges the saved interval. The root clips paint overflow so labels and playhead cannot expand scrollWidth. Ruler ticks and track grid share a nice time step that gets finer with zoom.

`timeline-data.js` provides clamped pointer-to-time conversion, drag deltas including scroll movement, and zoom anchoring to a visible playhead or viewport center. Pointer scrubbing uses the actual content rectangle, independent of native slider-thumb inset; keyboard range input retains native behavior. Zoom changes presentation only. Pointer cancellation discards an uncommitted drag. Stored times, snapshot data and the shared preview/export half-open timing logic are unchanged.
