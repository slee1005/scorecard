# Architecture and implementation decisions

## Repository inspection

The user-specified `scorecard/` directory was empty. The adjacent `shottracer/` project uses Python 3.13, FastAPI, Pillow/FFmpeg, plain JavaScript, file-backed projects and a separate mobile port. It has no shared hosted authentication/database service for this new editor. Existing source and the user's modified Xcode project were left untouched.

The implementation reuses that technology choice in a separate local application, rather than adding a cloud service or restructuring ShotTracer. React is used only for the new native Expo client. This preserves a buildless web editor and avoids coupling scorecard work to tracer analysis. These are independent applications; integrating tracer analysis into this editor would be a separate feature, not a completed capability.

## Boundaries

- `models`: validated golf, source-reference, video, overlay and styling data; pure scoring and timeline functions. All course values begin unknown. Scores remain optional. Half-open timeline intervals avoid two overlays at exact cuts.
- `storage`: SQLite/WAL with parameterized queries. Project JSON plus an independent revision column support compare-and-swap writes. Reusable course versions are immutable rows. Imported course snapshots in rounds are server-managed; round edits are separate overrides. Jobs persist independently.
- `graphics`: Pillow renders transparent PNG panels. Preview consumes these PNGs, and FFmpeg consumes the same panels scaled to output resolution. A single logical coordinate system respects source aspect ratio. No external fonts/assets are downloaded at runtime.
- `rendering`: ffprobe determines display dimensions, accounting for rotation. A single background worker freezes the submitted project revision, generates panels, uses half-open FFmpeg overlay expressions, encodes H.264/AAC, records actual progress and cleans scratch assets. Source and output video timing remain unretimed. Exports retain only the first audio track. Output is SDR yuv420p; HDR/color-managed editing is not promised.
- `api`: versioned local endpoints, bounded uploads, restricted Host/Origin and opaque server-owned source/reference paths. Video file responses support HTTP range requests. All file/SQLite work stays on the user's device.
- `web`: no framework/build requirement. A serialized save queue preserves revisions; HTML values are escaped. Native HTML video is the playback clock. Raster layers reuse export output; CSS handles placement only. Pointer gestures operate on the video rectangle, not the preview well.
- `mobile`: Expo Router root with five native workspace screens, generated OpenAPI input contracts, SQLite cache/outbox and optimistic revision sync. The server remains the scoring authority. Defaults in request schemas are optional, so the client treats persisted top-level project fields as required. Actual native runtime/device validation remains pending.

## Local versus hosted deployment

This is intentionally a loopback service. iOS simulator and Android USB/emulator port reversal can use the same local server and SQLite database. No network binding flag is provided. Host and Origin checks are defense in depth, not user authentication.

A production shared web/iOS/Android service requires a separately authorized architecture step: OIDC/session authentication and project ownership, HTTPS, object storage with scoped uploads, upload quotas/rate limits, durable render workers, credential handling, resumable uploads and push notifications. Merely changing the host to 0.0.0.0 would not implement these controls and is not the supported mobile production workflow.

## USGA integration boundary

Public NCRDB lookup is a user-opened link. The website did not establish permission for a reusable automated data feed, and the WHS programme documents controlled API participation. The app implements manual entry and authorized CSV/JSON import. It makes no backend network call or undocumented API assumption.

An eventual provider adapter must return tee/category-specific published values and independent provenance. Hole-level data must come from an authorized hole-level source. It must create a new local course version and require explicit round replacement; it cannot mutate an existing snapshot or infer hole yardages from aggregate length.

Research references (checked 2026-11-04):
- https://ncrdb.usga.org/courseTeeInfo.aspx
- https://www.whs.com/articles/2024/2024-interoperability.html
- https://expo.dev/changelog/sdk-56

## Testing contract

Use a temporary `GVS_HOME`; never point tests or synthetic uploads at real user data. Export tests generate tiny videos in pytest scratch space and inspect codecs, audio/video alignment and overlay pixels. The web UI has been manually exercised with a separate temporary home. Native JS bundle/type checks do not establish native compile, permission, playback or offline behavior on a phone.
