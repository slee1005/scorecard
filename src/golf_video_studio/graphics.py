from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont
from .models import Overlay, Project, classification, numbered_shots, totals


@lru_cache(maxsize=128)
def font(size: int, family: str = "sans"):
    candidates = {
        "sans": ["/System/Library/Fonts/AppleSDGothicNeo.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/malgun.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"],
        "serif": ["/System/Library/Fonts/Supplemental/Georgia.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "C:/Windows/Fonts/georgia.ttf"],
        "mono": ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf"],
    }
    for path in candidates[family]:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def panel(p: Project, overlay: Overlay) -> Image.Image:
    """One raster source for browser preview and FFmpeg: no CSS font drift."""
    s = overlay.style
    aspect = p.video.width / p.video.height if p.video else 16 / 9
    # A fixed logical height preserves glyph proportions on portrait sources too.
    logical_height = 1080
    logical_width = max(240, round(logical_height * aspect))
    w, h = max(1, round(s.width * logical_width)), max(1, round(s.height * logical_height))
    image = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(image)
    fg, accent = s.color, s.accent
    if s.panel:
        d.rounded_rectangle((0, 0, w-1, h-1), radius=s.radius, fill=(*ImageColor.getrgb(s.background), round(s.opacity * 255)))
    d.rectangle((0, s.radius, 5, h-s.radius), fill=accent)
    pad = min(28, w // 18)

    def text(x, y, value, size=s.font_size, fill=fg, max_width=None):
        value = str(value)
        f = font(size, s.font)
        limit = max_width or w - x - pad
        while value and d.textlength(value, font=f) > limit:
            value = value[:-1]
        d.text((x, y), value, font=f, fill=fill)

    if overlay.type in ("shot", "minimal"):
        shot = next(x for x in p.shots if x.id == overlay.shot_id)
        hole = p.round.holes[shot.hole-1]
        n = numbered_shots(p)[shot.id]
        if s.show_course:
            text(pad, h*.07, p.round.course or "GOLF VIDEO STUDIO", max(12, round(s.font_size*.65)), accent)
        text(pad, h*.23, f"HOLE {shot.hole:02d}  /  PAR {hole.par or '—'}", s.font_size, accent)
        text(pad, h*.40, f"{n:02d}   {shot.club.upper()}", round(s.font_size*1.45))
        distance = f"{shot.distance:g} YDS" if shot.distance is not None else "— YDS"
        if overlay.type == "minimal":
            text(pad, h*.72, distance)
        else:
            remaining = f"{shot.remaining:g} YDS" if shot.remaining is not None else "— YDS"
            text(pad, h*.65, f"DISTANCE {distance}   /   LEFT {remaining}", max(12, round(s.font_size*.72)))
            tee = p.round.tee or "—"
            text(pad, h*.83, f"{tee.upper()} TEE  ·  {hole.yardage or '—'} YDS  ·  {shot.result}", max(12, round(s.font_size*.58)))
    else:
        r = p.round
        items = r.holes[:9] if overlay.type == "front" else r.holes[9:] if overlay.type == "back" else r.holes
        count = len(items)
        total = totals(items)
        labelw = max(65, w*.13)
        cell = (w - labelw - pad*2) / (count+1)
        fsize = min(s.font_size, max(12, int(cell*.5)))
        title = (r.course or "SCORECARD") if s.show_course else "SCORECARD"
        text(pad, h*.06, title.upper(), min(s.font_size, max(14, int(h*.12))), accent)
        text(pad, h*.23, f"{r.player or 'PLAYER'}  /  {r.tee or '—'}  /  CR {r.rating or '—'}  /  SLOPE {r.slope or '—'}", max(11, int(h*.075)))
        rows = [("HOLE", [q.number for q in items], "TOT"), ("PAR", [q.par for q in items], total['par']), ("YDS", [q.yardage for q in items], total['yardage']), ("SCORE", [q.score for q in items], total['score'])]
        for row, (label, values, last) in enumerate(rows):
            y = h*(.36 + row*.12)
            text(pad, y, label, fsize)
            for col, value in enumerate([*values, last]):
                x = pad + labelw + col*cell
                if row == 3 and col < count:
                    kind = classification(items[col].par, items[col].score)
                    if kind in ("birdie", "eagle", "under"):
                        d.ellipse((x-5, y-3, x+cell-3, y+fsize+5), outline=accent, width=2)
                        if kind == "eagle":
                            d.ellipse((x-8, y-6, x+cell, y+fsize+8), outline=accent)
                    elif kind in ("bogey", "double", "over"):
                        d.rectangle((x-5, y-3, x+cell-3, y+fsize+5), outline="#ffb58a", width=2)
                        if kind == "double":
                            d.rectangle((x-8, y-6, x+cell, y+fsize+8), outline="#ffb58a")
                text(x, y, value if value is not None else "—", fsize, accent if row == 0 else fg, cell-2)
        front, back = totals(r.holes[:9]), totals(r.holes[9:])
        relative = totals(r.holes)['relative']
        relative_text = '—' if relative is None else 'E' if relative == 0 else f'{relative:+d}'
        text(pad, h*.88, f"OUT {front['score'] if front['score'] is not None else '—'}    IN {back['score'] if back['score'] is not None else '—'}    TOTAL {totals(r.holes)['score'] if totals(r.holes)['score'] is not None else '—'}    ({relative_text})", max(11, int(h*.065)), accent)
    if s.overlay_opacity != 1:
        image.putalpha(image.getchannel("A").point(lambda a: round(a * s.overlay_opacity)))
    return image


def png(p: Project, overlay: Overlay) -> bytes:
    output = io.BytesIO()
    panel(p, overlay).save(output, format="PNG")
    return output.getvalue()
