"""Explicit, read-only GolfCourseAPI requests; credentials never enter project data."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import HTTPException
from pydantic import ValidationError

from . import storage
from .models import Course, Hole, Tee

BASE = "https://api.golfcourseapi.com"
COURSE_ID = re.compile(r"^[0-9abcdefghjkmnpqrstvwxyz]{8}$")
CACHE_SECONDS = 86400


def _settings_path():
    return storage.home() / "provider-settings.json"


def _local_key() -> str:
    try:
        data = json.loads(_settings_path().read_text())
        value = data.get("golfcourse_api_key", "") if isinstance(data, dict) else ""
        return value if isinstance(value, str) else ""
    except (OSError, ValueError):
        return ""


def key_status() -> dict:
    env = bool(os.environ.get("GOLFCOURSE_API_KEY", "").strip())
    local = bool(_local_key())
    return {"configured": env or local, "source": "environment" if env else "local" if local else "none"}


def configure(key: str | None) -> dict:
    if key is not None:
        if key_status()["source"] == "environment":
            raise HTTPException(409, "golf_api_environment_key")
        key = key.strip()
        if not key or len(key) > 4096 or any(c.isspace() for c in key):
            raise HTTPException(422, "golf_api_invalid_key")
    # NamedTemporaryFile is 0600, and replacement keeps the credential file private.
    fd, name = tempfile.mkstemp(prefix="provider-", dir=storage.home())
    try:
        with os.fdopen(fd, "w") as file:
            json.dump({"golfcourse_api_key": key or ""}, file)
        os.replace(name, _settings_path())
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return key_status()


def _key() -> str:
    key = os.environ.get("GOLFCOURSE_API_KEY", "").strip() or _local_key()
    if not key:
        raise HTTPException(400, "golf_api_key_missing")
    if len(key) > 4096 or any(c.isspace() for c in key):
        raise HTTPException(400, "golf_api_invalid_key")
    return key


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not let any redirect forward the Authorization header to another host.
        return None


def _download(path: str, key: str) -> dict:
    request = Request(BASE + path, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=12) as response:
            content = response.read(4 * 1024 * 1024 + 1)
        if len(content) > 4 * 1024 * 1024:
            raise ValueError("Response too large")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Unexpected JSON shape")
        return data
    except HTTPError as exc:
        code = {401: "golf_api_unauthorized", 403: "golf_api_forbidden", 404: "golf_api_not_found", 429: "golf_api_rate_limited"}.get(exc.code, "golf_api_unavailable")
        status = exc.code if exc.code in (401, 403, 404, 429) else 502
        raise HTTPException(status, code) from None
    except (TimeoutError, URLError):
        raise HTTPException(503, "golf_api_timeout") from None
    except (OSError, ValueError):
        raise HTTPException(502, "golf_api_invalid_data") from None


def _fetch(path: str, refresh: bool = False) -> tuple[dict, bool]:
    key = _key()
    cached = storage.provider_cache_get(path)
    if cached and not refresh and time.time() - cached["time"] < CACHE_SECONDS:
        return cached["data"], True
    data = _download(path, key)
    if path.startswith("/v1/search?"):
        if not isinstance(data.get("courses"), list):
            raise HTTPException(502, "golf_api_invalid_data")
    else:
        normalize(data, path.rsplit("/", 1)[-1])
    storage.provider_cache_put(path, data)
    return data, False


def search(query: str) -> dict:
    query = query.strip()
    if not 2 <= len(query) <= 160:
        raise HTTPException(422, "golf_api_query_required")
    data, cached = _fetch("/v1/search?" + urlencode({"search_query": query, "fuzzy_match": "true"}))
    courses = data.get("courses")
    if not isinstance(courses, list):
        raise HTTPException(502, "golf_api_invalid_data")
    results = []
    for item in courses:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id", "")).lower()
        if not COURSE_ID.fullmatch(cid):
            continue
        location = item.get("location") or {}
        tees = item.get("tees") or {}
        if not isinstance(location, dict) or not isinstance(tees, dict):
            raise HTTPException(502, "golf_api_invalid_data")
        results.append({"id": cid, "name": str(item.get("course_name") or item.get("club_name") or cid)[:160],
                        "club": str(item.get("club_name") or "")[:160],
                        "city": str(location.get("city") or "")[:80], "state": str(location.get("state") or "")[:80],
                        "country": str(location.get("country") or "")[:80],
                        "tee_count": sum(v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else len(v) if isinstance(v, list) else 0 for v in tees.values())})
    return {"items": results[:100], "total": len(results), "cached": cached}


def normalize(data: dict, course_id: str) -> Course:
    """Map published tee/category and ordered holes; do not infer missing holes."""
    try:
        data = data.get("course", data)
        if not isinstance(data, dict) or str(data.get("id", "")).lower() != course_id:
            raise ValueError("Mismatched course")
        location = data.get("location") or {}
        tees = []
        for category, items in (data.get("tees") or {}).items():
            if category not in ("male", "female") or not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                raw_holes = item.get("holes") or []
                if not isinstance(raw_holes, list) or len(raw_holes) > 18:
                    raise ValueError("Unsupported hole count")
                values = [Hole(number=n + 1, par=h.get("par"), yardage=h.get("yardage"), handicap=h.get("handicap")) for n, h in enumerate(raw_holes)]
                values += [Hole(number=n) for n in range(len(values) + 1, 19)]
                tees.append(Tee(id=f"gca-{category}-{index}", name=item["tee_name"], category=category,
                    par=item.get("par_total"), yardage=item.get("total_yards"), rating=item.get("course_rating"),
                    slope=item.get("slope_rating"), holes=values))
        return Course(name=data.get("course_name") or data["club_name"], club=data.get("club_name") or "",
            city=location.get("city") or "", state=location.get("state") or "", country=location.get("country") or "",
            source_name="GolfCourseAPI", source_url=f"{BASE}/v1/courses/{course_id}", external_id=course_id,
            verification="imported", tees=tees)
    except (AttributeError, TypeError, KeyError, ValueError, ValidationError):
        raise HTTPException(502, "golf_api_invalid_data") from None


def import_course(course_id: str, refresh: bool = False) -> Course:
    course_id = course_id.lower()
    if not COURSE_ID.fullmatch(course_id):
        raise HTTPException(422, "golf_api_not_found")
    data, _ = _fetch(f"/v1/courses/{course_id}", refresh)
    course = normalize(data, course_id)
    content = course.model_dump(exclude={"id", "updated_at"})
    if not refresh:
        for existing in reversed(storage.courses()):
            if existing.model_dump(exclude={"id", "updated_at"}) == content:
                return existing
    # New immutable version; users apply its tee explicitly through the existing workflow.
    return storage.save_course(course)
