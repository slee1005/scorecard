**English** | [한국어](README.ko.md)

# Golf Video Studio

A local golf-video editor for timed shot graphics, editable 18-hole scorecards and permanent MP4 overlays. Video processing and project storage run on your own device. The web editor and Expo mobile development client share one FastAPI backend and scoring model.

![Golf Video Studio editor](docs/images/studio.jpg)

## Current status

| Component | Status |
| --- | --- |
| Desktop web editor | Video import/playback, round and shot editing, timeline, overlay design and saved projects implemented |
| MP4 export | Real FFmpeg H.264/AAC rendering, progress and download; shared preview/export graphics |
| Course library | Local search, tee/category selection, manual entry and authorized CSV/JSON imports |
| GolfCourseAPI | API-key settings, online name search, tee/category and hole imports, 24-hour cache; a valid user key is required |
| iOS / Android | Expo development client prepared; TypeScript checks and both JavaScript bundles passed; native builds and device validation pending |
| USGA / cloud | Live USGA integration, hosted authentication/storage and store publication pending |

**Validation:** 129 backend tests and 12 JavaScript tests passed, including synthetic video/audio export and preview-panel comparison. Browser checks covered upload, shot overlays, autosave and completed MP4 export. See [implementation status](docs/STATUS.md) and [architecture](docs/ARCHITECTURE.md).

## Run

Requires Python 3.13+, [uv](https://docs.astral.sh/uv/) and FFmpeg **with ffprobe and libx264** on PATH.

```bash
git clone https://github.com/slee1005/scorecard.git
cd scorecard
uv sync --locked
uv run golf-video-studio
```

Open [http://127.0.0.1:8775](http://127.0.0.1:8775). Use `--port 8780` for another port. On macOS, install FFmpeg with `brew install ffmpeg`. On Windows/Linux, install FFmpeg for your platform and put both executables on PATH. No frontend build, cloud account or API key is required.

## Editing workflow

1. Create a project and import an MP4, MOV or WebM. One source video belongs to each project. Metadata includes orientation-corrected dimensions, duration, FPS and audio presence. Browser playback depends on browser codec support; H.264 MP4 is the most portable input.
2. Enter the player, course, tee, rating category, date and optional published rating/slope. Open **Round & scorecard** to enter all 18 pars, yardages and scores. Unknown values stay blank. Front/back/overall totals show entered holes only; relative-to-par includes only scored holes with a known par.
3. Add shots with club, hole, distance, remaining distance, result, notes and start/end times. Shots are automatically numbered per hole in list order. Set **Shot number** (1–99) to override the displayed number, or leave it blank to restore automatic numbering. Manual numbers stay fixed when reordering; they do not renumber other shots. Move them up/down to reorder. Newly added shots use the next available time after the last shot; edit timestamps or drag timeline markers to move them.
4. Add a full/front/back scorecard. Select a timeline graphic and use **Design** to choose its template, adjust timing, normalized position/size, font, text/panel/accent colors, panel opacity, radius, visibility and course label. Drag panels and their resize handle directly in the preview. Choose Broadcast blue, Forest, Ocean, Paper, Crimson or Midnight color themes, or set custom colors. **Overlay transparency** ranges from 0% (visible) to 100% (fully transparent) and affects the entire graphic, while **Panel opacity** affects only the background. Theme changes preserve transparency, timing and placement. Save styles as project presets. Shot and scorecard panels can coexist in separate areas; timing/panel collisions are rejected.
5. Use play/pause, seek, frame steps and timeline zoom. Space toggles playback; arrow keys step frames when no form control has focus. The actual video `currentTime` controls overlay visibility with half-open `[start, end)` intervals. The scrubber, ruler, playhead and both marker rows share one zoomed/scrolled time axis. Zoom preserves the visible playhead location (or viewport center when it is off screen); short markers show their exact duration. Seek and drag coordinates include zoom and horizontal scrolling.
6. Select **Export MP4**, choose draft/high/master quality and source/1080p/4K bounds. Source aspect ratio and audio are preserved, video is encoded as H.264/yuv420p and the first audio track as AAC. Export never upscales. Progress comes from FFmpeg; download the finished MP4 from Exports.

**Default layout:** new shot popups use X **0.75**, Y **0.03**, width **0.2**, height **0.15**; new full/front/back scorecards use X **0.24**, Y **0.2**, width **0.504**, height **0.56**. Both use font size **30**, corner radius **20**, sans font, visible background and course information. Coordinates are normalized to the video frame and remain the same in portrait/landscape. Web/native creation and Design RESET use these defaults. Saved styles are retained; the separate recommended-layout action still fits the design aspect to the source frame.

**Putter remaining distance:** choosing **Putter** switches the remaining-distance input and broadcast card to **feet (FT)**. Other clubs use yards. Enter 8 to show **8 FT**; switching a saved 10-yard distance to Putter shows **30 FT** and switching back shows 10 yards. Values remain stored in yards for backward compatibility and API clients; no old project data is relabeled as feet. Unknown distance stays blank/— FT. Total hole yardage, individual shot distance and scorecards retain yards. Web/native entry and shared preview/MP4 rendering use this conversion; club and distance changes remain undoable.

**Broadcast graphics:** shot popups now show the round player name, relative-to-par score through the holes before the shot’s current hole, hole/par, large remaining distance, a large shot number, and a lower strip with club and total hole yardage. The broadcast layout enlarges HOLE, PAR, LEFT, TO PAR and club labels/text; the overall font-size control scales them together. Total hole yardage comes from the selected hole; it is separate from the individual shot distance. The current and later holes are excluded even when their scores have already been entered. Hole 1 starts at E; any missing prior-hole score/par leaves cumulative score unknown. Missing hole par/yardage stays unknown. The minimal template continues to show individual shot distance.

![Broadcast shot popup — synthetic example](docs/images/broadcast-shot.png)

**Modern scorecards:** the full card uses two aligned nine-hole sections, with par, yardage, scores, front/back totals, overall par/score and score indicators. Front/back templates show one nine-hole section. Birdie/eagle circles and bogey/double-bogey squares use exactly the same center as the actual rendered digit ink, including double-digit scores and missing-value dashes. Editable score fields also center their symbols independently of the input border.

![Modern 18-hole scorecard — synthetic example](docs/images/broadcast-scorecard.png)

New graphics use an aspect-aware recommended layout. Existing saved colors, sizes, timing and alpha values are retained. For an older wide/flat card, select it in **Design → Use recommended layout**, then resize/drag if needed. **Apply colors to all graphics** copies the selected popup's three colors across the project without changing timing, position, fonts or transparency. Native previews receive the same updated server-generated panels.

The same Pillow-generated RGBA panels are displayed in the browser and composited into exports. Coordinates use the actual video rectangle, including portrait clips, rather than the surrounding letterbox. For portrait videos, use front/back scorecards or enlarge the panel for legibility. The preview is a video plus transparent image layers; `requestAnimationFrame` runs only while playing. These image layers deliberately share their source with the renderer instead of maintaining a second canvas text implementation.

## Courses and data integrity

### GolfCourseAPI setup

Open **Course library → GolfCourseAPI connection**, enter your key and select **Save API key**. Search by course or club name using **Search online** (or Enter), then **Save course & tees**. Select the tee and its published `male`/`female` rating category from the saved course card, and choose **Use selected tee**. The normal replacement confirmation protects current round values and preserves scores. [Official API documentation](https://api.golfcourseapi.com/docs/api/) describes the provider data and account requirements.

Search uses `GET /v1/search?search_query=…`; detail uses `GET /v1/courses/{id}` with `Authorization: Bearer …`. Only the local backend calls the provider, on explicit search/import/refresh actions. Search returns tee counts; importing a selected course loads full tee ratings, total yardage/par and available hole par/yardage/handicap. Missing holes stay unknown. Imports are labeled **GolfCourseAPI / imported**, not USGA-verified. **Fetch latest version** creates a new saved course version; applying it to a round is a separate confirmed action. Search/detail responses are cached locally for 24 hours. Bad keys, plan restrictions, rate limits and connectivity errors are reported without exposing the key.

Keys are never returned to the browser, saved in browser storage, embedded in project JSON, or committed. A saved key lives in `GVS_HOME/provider-settings.json` with owner-only permissions (0600); this is a local credential file, not encrypted storage. Use **Remove saved key** to clear it. Alternatively set `GOLFCOURSE_API_KEY` in the server environment; it takes precedence and cannot be replaced through the UI. Keep the credential file out of shared backups. No real key is shipped. Integration tests use synthetic provider responses; a live account lookup must be verified with your own key.

Course search searches the **saved local course library**, including name, club, city, state and ZIP. A course can contain multiple tees and rating categories. Save the current round's course configuration, or import an authorized course JSON file. Choose the exact tee/category before applying it. Confirmation is required before course values are replaced; round scores are retained.

The official [USGA course lookup](https://ncrdb.usga.org/courseTeeInfo.aspx) is linked in the app. No public API authorization was available for this project. The [WHS interoperability programme](https://www.whs.com/articles/2024/2024-interoperability.html) describes controlled access and use restrictions. There is **no automated USGA lookup, scraping, invented course data, or claim of USGA verification**. A licensed integration remains a future adapter.

Imported course snapshots are immutable references. Round overrides are stored separately; the UI marks manual overrides and exposes the original snapshot. Course imports are labeled unverified. Hole-level data must be entered or imported; totals never generate fictitious hole values.

CSV columns: `hole,par,yardage,score,handicap`. Use 1–18 unique rows, UTF-8, and integer values; empty cells clear values in supplied columns. Missing columns retain existing values. Import validation is atomic. Download an empty 18-hole template in the app. Upload PNG/JPG/PDF scorecards (up to 15 MB) for reference; OCR and automatic verification are not included.

For JSON imports, use the `Course` schema in [docs/openapi.json](docs/openapi.json), also available at `/docs`. Minimal valid input:

```json
{"name":"Your course","source_name":"User scorecard","verification":"imported","tees":[{"name":"Your tee","category":"Applicable category"}]}
```

This initializes 18 unknown holes, not guessed data. Supply `holes` with exactly one of each number 1–18 to import hole information. Optional tee fields include total `par`, `yardage`, `rating`, `slope`, `bogey_rating`, `front_rating`, `back_rating`, `front_slope`, `back_slope`. Source metadata includes `source_url`, `external_id`, city/state/country/ZIP and update time. To refresh a course, import a new saved version and explicitly apply its tee; originals remain preserved.

## Storage and API

Projects and reusable courses are stored in `~/.golf-video-studio/studio.sqlite`; source videos/references/exports live in its `projects/<id>/` directory. Set `GVS_HOME` to an independent data directory (always do this for experiments). `GVS_MAX_UPLOAD_MB` defaults to 8192. JSON project backups can be downloaded from **Getting started**. A backup does not include source video; copy the data directory while the server is stopped for a complete backup.

All APIs use `/api/v1`; interactive API documentation is at `/docs`. SQLite revisions prevent stale updates: `PUT /projects/{id}` requires the last revision and returns 409 on a conflict. The UI retains the conflicting draft in memory and offers JSON download before reload. There is a single render worker and at most three queued/running exports. Export jobs persist; interrupted jobs are marked failed on restart. Completed exports older than 24 hours are removed on next startup; source videos are retained. Temporary rendering assets are removed after each job.

The server binds **127.0.0.1 only**. It rejects other Host values and cross-origin requests. The only outbound backend requests are explicit authenticated GolfCourseAPI course reads when configured. There are no user accounts, telemetry, cloud storage or production authentication. Do not expose this unauthenticated development server to the internet.

## Mobile development

`mobile/` contains an Expo SDK 56 / React Native / TypeScript development client with Home, Courses, Rounds, Videos and Profile screens. It uses generated API types and the same backend, course library, score calculations and exported overlay PNGs. SQLite caches projects/courses and queues offline round/shot edits. Sync uses revisions, retains conflicts and requires explicit draft discard to accept newer server data. Totals remain the last server totals while offline; no second scoring engine exists on the phone.

```bash
cd mobile
npm ci
npm run typecheck
npm run ios       # macOS + Xcode + simulator
# or: adb reverse tcp:8775 tcp:8775
npm run android   # Android SDK / emulator or attached device
```

Use development builds, not Expo Go alone. `lib/repository.ts` uses loopback at port 8775: iOS simulator or Android `adb reverse` can reach the desktop backend. A physical iPhone cannot access this loopback server directly. Application identifiers are **development placeholders**; replace them with owned identifiers before release. `eas.json` prepares development APK, internal preview and production AAB profiles; no signing credentials, EAS project or publication is assumed.

Native round screens also support manual shot-number overrides. Native code includes device document-video selection, actual upload progress, playback, saved overlay preview, server export submission/progress and download links. The web editor supplies detailed timing/design. Native builds/device behavior and offline conflict interaction still need device validation. Authentication/SecureStore, HTTPS multi-user hosting, private cloud storage, background/resumable upload, push notifications, touch overlay design, local language support and store release are **not implemented**. See [docs/STATUS.md](docs/STATUS.md).

## Verification

```bash
uv run pytest
node --test tests/test_editor_data.mjs tests/test_timeline_data.mjs
cd mobile
npm ci
npm run typecheck
npx expo install --check
npx expo export --platform ios --platform android
```

Tests cover scoring and partial-round totals, score categories, shot numbering, half-open visibility, collisions/bounds, optimistic concurrency, atomic CSV imports, course snapshots/overrides, Host/Origin checks, RGBA panels, portrait proportions, restart recovery, and a real FFmpeg MP4 export with synthetic video/audio. The export test checks codecs, audio/video start and duration, timed graphic presence/absence and frame similarity with the shared preview panel. GolfCourseAPI tests verify credential isolation, HTTP error redaction, caching, exact tee/category mapping, missing holes and immutable refreshes. Theme/numbering/layout tests and the real export cover manual shot numbers, global alpha and simultaneous modern shot/full-scorecard graphics. Pixel tests verify marker/digit centers for three font families; layout tests cover portrait and landscape footage. Tests make no live provider calls, and test videos are not committed. Mobile JS bundling is not a signed native build or on-device test.

## Scorecard snapshots

**Add scorecard snapshot** previews the current hole, completed count, front/back scores, current total and relative score before confirmation. Each full/front/back card captures independent player/course/tee and all 18 holes at that revision. Unplayed holes remain dashes; the current hole is highlighted. **Played par** includes completed holes only and is separate from **Course par**. An unknown completed-hole par leaves relative score unknown.

Timeline labels show the captured hole count and version. Select a card in **Design** to inspect its creation time, original insertion time and captured scores. Moving, resizing, changing duration, colors or transparency never refreshes its data. **Create new scorecard snapshot** captures a later state. **Replace snapshot data** requires confirmation, changes only the selected overlay and retains its previous versions for inspection. A score change in another window invalidates an open confirmation; reload and preview again.

Existing live cards are frozen once from their currently saved round and labeled migrated snapshots; original insertion-time scores cannot be reconstructed. This upgrade increments the project revision, so old offline drafts must resolve a conflict rather than overwrite the migration. Deleted overlays retain their captured history in the project backup. Each project supports up to 1,000 captures including previous versions. One project contains one round; its project ID is also the snapshot round ID.

The Expo Videos screen uses the same revision-checked capture/replace APIs, confirmation summaries, version history and backend PNG rendering as the web editor. Insert at the current native playhead; use the web editor for detailed timing and styling. Capturing requires a successful sync/connection. Automated tests cover 5/9/18-hole captures, later corrections, explicit replacement, migration, immutable fields, completed-only totals and three historical cards pixel-compared against an actual MP4 export. Native TypeScript/bundle checks do not establish iOS/Android device behavior; device acceptance testing remains pending.

## Project trash and edit history

Use **Delete project** in the top bar to move the selected project to **Project trash** after confirmation. The sidebar places **Project trash** and **Getting started** directly below **New project**, all as equally sized buttons. Restore it from the trash button. Source video, exported files, scorecard snapshots and edit history remain on this device; this action does not reclaim disk space. **Empty trash** permanently removes every listed project, original video, reference file, export, scorecard snapshot and edit history after a second confirmation. It cannot be restored or undone. The dialog shows project names/count; if trash contents change before confirmation the request is rejected for review. Projects with queued/running exports cannot be deleted. Trashed projects are hidden from the workspace and reject editing, playback and new exports until restored. Deleting the last active project opens a new blank workspace. Check projects and choose **Permanently delete selected**, or use the **Permanently delete** button on an individual row. The confirmation lists only the selected targets, and other trash stays recoverable. Unrelated additions to trash do not change a selected deletion; stale/restored targets reject the whole selection. Only trashed projects are eligible for permanent deletion; active projects, shared courses and API-key settings are preserved. If file locks delay cleanup, the UI shows a pending status and a retry button. Cleanup resumes after restart; pending cleanup must finish before disk space is fully reclaimed.

Each **Round / Shot / Design** inspector tab has independent **UNDO / REDO / RESET** controls. The latest 100 edits per section are stored in SQLite and survive reloads and project switching. A new edit clears only that section's redo branch. Project naming, source video/reference uploads and provider key settings are outside this history. The controls operate on the whole section, including all shots or all graphic styles, rather than just the selected item.

- **Round RESET:** clears player/date/manual round entries and scores; restores imported course/tee defaults when available.
- **Shot RESET:** removes all shots and their popups, preserving scorecards, round scores and source video.
- **Design RESET:** restores factory colors, fonts, transparency and aspect-aware positions/sizes for all graphics. Timing, templates, saved presets and captured scores are preserved. Layout collisions reject the reset without changes.

RESET requires confirmation and is one undoable edit. Scorecard insertion, deletion and explicit data replacement can also be undone/redone through Design history without recapturing scores or deleting immutable snapshots. Round and shot history never refresh historical card data. If another section now depends on an edited object, undo the dependent edit first; stale revisions and invalid restored layouts are rejected without consuming history.

Outside text inputs, **⌘/Ctrl+Z** undoes and **⌘/Ctrl+Shift+Z** or **Ctrl+Y** redoes the active section (Round on the scorecard page). Inputs keep native text undo. These controls and the trash interface are implemented in the web editor. Shared API history also records native outbox saves by section; native history/trash controls are not yet implemented. Edit history lives in the local database, not the downloadable project JSON backup.

## Structure

- `src/golf_video_studio/models.py`: validated domain/timeline/style models and scoring.
- `storage.py`: SQLite persistence, revisions, courses and jobs.
- `graphics.py`: shared overlay raster generation.
- `rendering.py`: probing, job queue, FFmpeg processing and recovery.
- `api.py`: local HTTP API and streaming file responses.
- `web/`: responsive English/Korean editor, no build step.
- `mobile/`: Expo development client and offline repository.
- `docs/`: API contract, architectural decisions and explicit completion status.

The Python dependencies are locked with `uv.lock`; mobile dependencies with `package-lock.json`. FFmpeg is an external prerequisite. Source input codecs and fonts vary by system; install a Korean-capable font on Linux/Windows when rendering Korean labels. Player comparison, multi-video assembly, waveform editing, HDR preservation, OCR and cloud/mobile production features are future work.
