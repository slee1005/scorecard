"""One immutable score capture path for web, mobile, preview and export."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from .models import Project, ScorecardData, ScorecardSnapshot, SnapshotHole, Style, snapshot_totals, uid, default_style


def capture(p: Project, position: float, current_hole: int | None = None, *,
            previous: ScorecardSnapshot | None = None, legacy: bool = False,
            snapshot_id: str | None = None) -> ScorecardSnapshot:
    r = p.round
    if current_hole is None:
        current_hole = next((h.number for h in r.holes if h.score is None), None)
    if current_hole is not None and r.holes[current_hole-1].score is not None:
        raise HTTPException(422, 'snapshot_current_completed')
    holes = tuple(SnapshotHole(number=h.number, par=h.par, score=h.score, yardage=h.yardage,
        handicap=h.handicap, status='completed' if h.score is not None else 'current' if h.number == current_hole else 'not_played',
        relative_to_par=h.score-h.par if h.score is not None and h.par is not None else None) for h in r.holes)
    data = ScorecardData(player=r.player, course=r.course, date=r.date, tee=r.tee, category=r.category,
        rating=r.rating, slope=r.slope,
        course_par=sum(h.par for h in holes) if all(h.par is not None for h in holes) else r.total_par,
        published_course_par=r.total_par,
        total_yardage=sum(h.yardage for h in holes) if all(h.yardage is not None for h in holes) else r.total_yardage,
        source_name=r.reference.source_name if r.reference else 'Manual',
        source_url=r.reference.source_url if r.reference else '',
        reference_course_id=r.reference.id if r.reference else None, holes=holes)
    return ScorecardSnapshot(id=snapshot_id or uid(), project_id=p.id, round_id=p.id,
        timeline_position=position, created_at=datetime.now(timezone.utc).isoformat(),
        snapshot_version=previous.snapshot_version+1 if previous else 1,
        previous_snapshot_id=previous.id if previous else None, legacy=legacy,
        current_hole=current_hole, scorecard_data=data, **snapshot_totals(holes))


def card_style(p: Project, kind: str) -> Style:
    return default_style(kind)
