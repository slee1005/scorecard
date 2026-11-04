# Completion status

This status distinguishes working desktop implementation from native preparation and external integration dependencies.

| Area | Status |
| --- | --- |
| Project creation, switching, naming and persistence | Implemented; SQLite + revisions |
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
| Course library search, multi-tee/category selection | Implemented against saved local data |
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

- Backend suite: 21 tests, including a real FFmpeg export of synthetic video with audio, RGBA panel equality, timeline boundaries, portrait proportions, course reference immutability and optimistic-write conflicts.
- Existing adjacent ShotTracer suite: 92 tests passed; source was not edited.
- Browser QA uses a temporary data home: Korean workspace render, real keyboard round entry/autosave, synthetic video upload, shot creation, preview graphics and real export submission/download readiness.
- Source and mobile lockfiles are retained for reproducibility. See README commands for rerunning validation.

## Next development milestones

1. Run the development client on iOS simulator and Android emulator; exercise offline changes, reconnect, cross-client conflicts and native video upload/playback.
2. Add native touch timing/design, mobile translations, conflict merge/export UX and gallery/share integration.
3. Establish a licensed course-data provider or USGA programme access; add a provider adapter with tests and explicit provenance.
4. Design hosted authentication/authorization/storage/render infrastructure before exposing a shared production endpoint.
5. Build signed device artifacts, verify background behavior and store privacy declarations, then prepare store submissions with owner-provided accounts.
