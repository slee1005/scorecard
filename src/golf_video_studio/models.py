from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, model_validator


def uid() -> str:
    return uuid4().hex


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


CLUBS = ["Driver", "3 Wood", "5 Wood", "3 Hybrid", "4 Hybrid", "3 Iron", "4 Iron", "5 Iron", "6 Iron", "7 Iron", "8 Iron", "9 Iron", "PW", "GW", "SW", "LW", "Putter"]


class Hole(Model):
    number: int = Field(ge=1, le=18)
    par: int | None = Field(default=None, ge=3, le=6)
    yardage: int | None = Field(default=None, ge=1, le=1000)
    score: int | None = Field(default=None, ge=1, le=40)
    handicap: int | None = Field(default=None, ge=1, le=18)


def holes() -> list[Hole]:
    # Unknown course values remain unknown until entered or imported.
    return [Hole(number=n) for n in range(1, 19)]


class Tee(Model):
    id: str = Field(default_factory=uid, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(default="", max_length=80)
    par: int | None = Field(default=None, ge=27, le=108)
    yardage: int | None = Field(default=None, ge=500, le=15000)
    rating: float | None = Field(default=None, ge=20, le=100)
    slope: int | None = Field(default=None, ge=55, le=155)
    bogey_rating: float | None = Field(default=None, ge=20, le=150)
    front_rating: float | None = Field(default=None, ge=10, le=60)
    back_rating: float | None = Field(default=None, ge=10, le=60)
    front_slope: int | None = Field(default=None, ge=55, le=155)
    back_slope: int | None = Field(default=None, ge=55, le=155)
    holes: list[Hole] = Field(default_factory=holes, min_length=18, max_length=18)

    @model_validator(mode="after")
    def unique_holes(self):
        if sorted(h.number for h in self.holes) != list(range(1, 19)):
            raise ValueError("Exactly one of each hole 1–18 is required")
        self.holes.sort(key=lambda h: h.number)
        if any(h.score is not None for h in self.holes):
            raise ValueError("Course templates cannot contain round scores")
        return self


class Course(Model):
    id: str = Field(default_factory=uid, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=160)
    club: str = Field(default="", max_length=160)
    city: str = Field(default="", max_length=80)
    state: str = Field(default="", max_length=80)
    country: str = Field(default="", max_length=80)
    zip_code: str = Field(default="", max_length=20)
    source_name: str = Field(default="Manual", max_length=160)
    source_url: str = Field(default="", max_length=1000)
    external_id: str = Field(default="", max_length=120)
    verification: Literal["manual", "imported"] = "manual"
    updated_at: str = ""
    tees: list[Tee] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_tees(self):
        if len({t.id for t in self.tees}) != len(self.tees):
            raise ValueError("Duplicate tee ids")
        return self


class Round(Model):
    player: str = Field(default="", max_length=120)
    course: str = Field(default="", max_length=160)
    date: str = Field(default_factory=lambda: date.today().isoformat(), pattern=r"^\d{4}-\d{2}-\d{2}$")
    tee: str = Field(default="", max_length=80)
    category: str = Field(default="", max_length=80)
    rating: float | None = Field(default=None, ge=20, le=100)
    slope: int | None = Field(default=None, ge=55, le=155)
    total_par: int | None = Field(default=None, ge=27, le=108)
    total_yardage: int | None = Field(default=None, ge=500, le=15000)
    holes: list[Hole] = Field(default_factory=holes, min_length=18, max_length=18)
    # Immutable imported snapshot; editable values above are the round's overrides.
    reference: Course | None = None
    reference_tee_id: str | None = None

    @model_validator(mode="after")
    def valid_round(self):
        date.fromisoformat(self.date)
        if sorted(h.number for h in self.holes) != list(range(1, 19)):
            raise ValueError("Exactly one of each hole 1–18 is required")
        self.holes.sort(key=lambda h: h.number)
        return self


class Shot(Model):
    id: str = Field(default_factory=uid, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    hole: int = Field(ge=1, le=18)
    number: int | None = Field(default=None, ge=1, le=99)
    club: str = Field(default="Driver", max_length=40)
    distance: float | None = Field(default=None, ge=0, le=1000)
    remaining: float | None = Field(default=None, ge=0, le=1500)
    result: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=2000)
    start: float = Field(default=0, ge=0, le=86400)
    end: float = Field(default=5, gt=0, le=86400)

    @model_validator(mode="after")
    def valid_shot(self):
        if self.end <= self.start:
            raise ValueError("Shot end must be after start")
        if self.club not in CLUBS:
            raise ValueError("Unknown club")
        return self


class Style(Model):
    x: float = Field(default=0.04, ge=0, le=1)
    y: float = Field(default=0.68, ge=0, le=1)
    width: float = Field(default=0.42, ge=0.15, le=1)
    height: float = Field(default=0.25, ge=0.12, le=1)
    background: str = Field(default="#101c26", pattern=r"^#[0-9a-fA-F]{6}$")
    color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#29c4b5", pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: float = Field(default=0.9, ge=0, le=1)
    overlay_opacity: float = Field(default=1.0, ge=0, le=1)
    radius: int = Field(default=14, ge=0, le=60)
    font_size: int = Field(default=24, ge=12, le=48)
    font: Literal["sans", "serif", "mono"] = "sans"
    panel: bool = True
    show_course: bool = True

    @model_validator(mode="after")
    def fit(self):
        if self.x + self.width > 1.00001 or self.y + self.height > 1.00001:
            raise ValueError("Overlay must fit within the video")
        return self


class FrozenModel(Model):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class SnapshotHole(FrozenModel):
    number: int = Field(ge=1, le=18)
    par: int | None = Field(default=None, ge=3, le=6)
    score: int | None = Field(default=None, ge=1, le=40)
    yardage: int | None = Field(default=None, ge=1, le=1000)
    handicap: int | None = Field(default=None, ge=1, le=18)
    status: Literal["completed", "current", "not_played"]
    relative_to_par: int | None = None

    @model_validator(mode="after")
    def coherent(self):
        if (self.status == 'completed') != (self.score is not None):
            raise ValueError('Only completed holes may have scores')
        expected = self.score - self.par if self.score is not None and self.par is not None else None
        if self.relative_to_par != expected:
            raise ValueError('Invalid captured hole comparison')
        return self


class ScorecardData(FrozenModel):
    player: str = Field(default="", max_length=120)
    course: str = Field(default="", max_length=160)
    date: str = ""
    tee: str = Field(default="", max_length=80)
    category: str = Field(default="", max_length=80)
    rating: float | None = None
    slope: int | None = None
    course_par: int | None = None
    published_course_par: int | None = None
    total_yardage: int | None = None
    source_name: str = ""
    source_url: str = ""
    reference_course_id: str | None = None
    holes: tuple[SnapshotHole, ...] = Field(min_length=18, max_length=18)

    @model_validator(mode="after")
    def ordered_holes(self):
        if [h.number for h in self.holes] != list(range(1,19)):
            raise ValueError('Snapshot requires ordered holes 1–18')
        return self


def snapshot_totals(items: tuple[SnapshotHole, ...]) -> dict:
    completed = [h for h in items if h.status == 'completed']
    def score(holes):
        values = [h.score for h in holes if h.status == 'completed']
        return sum(values) if values else None
    total = score(items)
    # An unknown played-hole par makes the comparison unknown, never guessed.
    par = sum(h.par for h in completed) if completed and all(h.par is not None for h in completed) else None
    return dict(completed_holes_count=len(completed), front_nine_score=score(items[:9]),
        back_nine_score=score(items[9:]), total_score=total, total_par=par,
        relative_to_par=total-par if total is not None and par is not None else None)


class ScorecardSnapshot(FrozenModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    project_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    round_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    timeline_position: float = Field(ge=0, le=86400)
    created_at: str
    snapshot_version: int = Field(default=1, ge=1)
    previous_snapshot_id: str | None = None
    legacy: bool = False
    current_hole: int | None = Field(default=None, ge=1, le=18)
    completed_holes_count: int = Field(ge=0, le=18)
    scorecard_data: ScorecardData
    front_nine_score: int | None
    back_nine_score: int | None
    total_score: int | None
    total_par: int | None
    relative_to_par: int | None

    @model_validator(mode="after")
    def valid_capture(self):
        for key, expected in snapshot_totals(self.scorecard_data.holes).items():
            if getattr(self,key) != expected:
                raise ValueError('Snapshot totals must match completed holes')
        current = [h.number for h in self.scorecard_data.holes if h.status == 'current']
        if current != ([] if self.current_hole is None else [self.current_hole]):
            raise ValueError('Invalid captured current hole')
        return self


class Overlay(Model):
    id: str = Field(default_factory=uid, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    type: Literal["shot", "minimal", "full", "front", "back"] = "shot"
    shot_id: str | None = None
    snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    start: float = Field(default=0, ge=0, le=86400)
    end: float = Field(default=5, gt=0, le=86400)
    visible: bool = True
    style: Style = Field(default_factory=Style)

    @model_validator(mode="after")
    def timing(self):
        if self.end <= self.start:
            raise ValueError("Overlay end must be after start")
        return self


class Video(Model):
    filename: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


class Project(Model):
    id: str = Field(default_factory=uid, pattern=r"^[a-f0-9]{32}$")
    name: str = Field(default="Untitled round", min_length=1, max_length=160)
    revision: int = Field(default=0, ge=0)
    created_at: str = ""
    updated_at: str = ""
    round: Round = Field(default_factory=Round)
    shots: list[Shot] = Field(default_factory=list, max_length=500)
    overlays: list[Overlay] = Field(default_factory=list, max_length=200)
    video: Video | None = None
    snapshots: dict[str, ScorecardSnapshot] = Field(default_factory=dict, max_length=1000)
    presets: dict[str, Style] = Field(default_factory=dict, max_length=30)
    reference_file: str | None = None

    @model_validator(mode="after")
    def consistency(self):
        shot_ids = {s.id for s in self.shots}
        if len(shot_ids) != len(self.shots) or len({o.id for o in self.overlays}) != len(self.overlays):
            raise ValueError("Duplicate shot or overlay ids")
        for o in self.overlays:
            if o.type in ("shot", "minimal") and o.shot_id not in shot_ids:
                raise ValueError("Shot overlay must refer to a shot")
            if self.video and o.end > self.video.duration + 0.05:
                raise ValueError("Overlay extends beyond video")
        if self.video and any(s.end > self.video.duration + 0.05 for s in self.shots):
            raise ValueError("Shot extends beyond video")
        enabled = sorted((o for o in self.overlays if o.visible), key=lambda o: o.start)
        for i, a in enumerate(enabled):
            for b in enabled[i + 1:]:
                if b.start >= a.end:
                    break
                if a.type in ("shot", "minimal") and b.type in ("shot", "minimal"):
                    raise ValueError("Shot overlays cannot overlap")
                # Different overlay types can coexist if their panels do not collide.
                if (a.style.x < b.style.x + b.style.width and b.style.x < a.style.x + a.style.width
                        and a.style.y < b.style.y + b.style.height and b.style.y < a.style.y + a.style.height):
                    raise ValueError("Overlapping overlay panels")
        # Old projects had live cards. Freeze their saved state once; the storage
        # loader persists this migration before allowing future round edits.
        from .snapshots import capture
        from uuid import NAMESPACE_URL, uuid5
        for overlay in self.overlays:
            if overlay.type in ('shot','minimal'):
                if overlay.snapshot_id is not None:
                    raise ValueError('Shot graphics cannot reference scorecard snapshots')
                continue
            if overlay.snapshot_id is None:
                key = uuid5(NAMESPACE_URL,f'gvs:{self.id}:{overlay.id}:legacy').hex
                snap = capture(self,overlay.start,legacy=True,snapshot_id=key)
                self.snapshots[key] = snap
                overlay.snapshot_id = key
            if overlay.snapshot_id not in self.snapshots:
                raise ValueError('Scorecard snapshot not found')
        if len(self.snapshots) > 1000:
            raise ValueError('Snapshot history limit reached')
        for key, snap in self.snapshots.items():
            if key != snap.id or snap.project_id != self.id or snap.round_id != self.id:
                raise ValueError('Snapshot belongs to another project or round')
            previous = self.snapshots.get(snap.previous_snapshot_id) if snap.previous_snapshot_id else None
            if snap.snapshot_version != (previous.snapshot_version + 1 if previous else 1):
                raise ValueError('Invalid snapshot history')
            if snap.previous_snapshot_id and previous is None:
                raise ValueError('Previous snapshot is missing')
        return self


def active_overlays(p: Project, time: float) -> list[Overlay]:
    """Half-open intervals avoid duplicate graphics on exact cut boundaries."""
    return [o for o in p.overlays if o.visible and o.start <= time < o.end]


def numbered_shots(p: Project) -> dict[str, int]:
    counts: dict[int, int] = {}
    result = {}
    # The list order is intentional and can be changed without changing timing.
    for shot in p.shots:
        counts[shot.hole] = counts.get(shot.hole, 0) + 1
        result[shot.id] = shot.number if shot.number is not None else counts[shot.hole]
    return result


def classification(par: int | None, score: int | None) -> str:
    if par is None or score is None:
        return "unknown"
    delta = score - par
    return {0: "par", -1: "birdie", -2: "eagle", 1: "bogey", 2: "double"}.get(delta, "under" if delta < 0 else "over")


def totals(items: list[Hole]) -> dict:
    played = [h for h in items if h.score is not None]
    relative = [h for h in played if h.par is not None]
    return {"score": sum(h.score for h in played) if played else None,
            "par": sum(h.par for h in items if h.par is not None) if any(h.par is not None for h in items) else None,
            "yardage": sum(h.yardage for h in items if h.yardage is not None) if any(h.yardage is not None for h in items) else None,
            "relative": sum(h.score - h.par for h in relative) if relative else None,
            "played": len(played), "rated_played": len(relative),
            "par_known": sum(h.par is not None for h in items),
            "yardage_known": sum(h.yardage is not None for h in items)}
