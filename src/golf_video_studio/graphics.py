from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont

from .models import Overlay, Project, Style, numbered_shots, totals, score_before_hole

Box = tuple[float, float, float, float]


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


def mix(a: str, b: str, amount: float) -> str:
    rgb = tuple(round(x * (1 - amount) + y * amount) for x, y in zip(ImageColor.getrgb(a), ImageColor.getrgb(b)))
    return '#%02x%02x%02x' % rgb


def is_light(color: str) -> bool:
    r, g, b = ImageColor.getrgb(color)
    return .2126 * r + .7152 * g + .0722 * b > 155


def relative_text(value: int | None) -> str:
    return '—' if value is None else 'E' if value == 0 else f'{value:+d}'


def show(value) -> str:
    return '—' if value is None else str(value)


@lru_cache(maxsize=2048)
def _ink_bounds(text: str, size: int, family: str):
    f = font(size, family)
    if hasattr(f, 'getmask2'):
        mask, offset = f.getmask2(text, mode='L')
        bounds = mask.getbbox()
        if bounds is None:
            return None
        return (offset[0] + bounds[0], offset[1] + bounds[1], offset[0] + bounds[2], offset[1] + bounds[3])
    return f.getbbox(text)


def centered_text(draw, box: Box, value, size: float, color, family: str = 'sans', align: str = 'center'):
    """Center rendered ink; font line metrics leave dashes and some digits off-center."""
    text = ' '.join(show(value).split())
    x0, y0, x1, y1 = box
    available_w, available_h = max(1, x1 - x0), max(1, y1 - y0)
    size = max(1, round(size))
    while True:
        bounds = _ink_bounds(text, size, family)
        if bounds is None:
            return
        left, top, right, bottom = bounds
        if right - left <= available_w and bottom - top <= available_h:
            break
        if size > 6:
            size -= 1
        elif len(text) > 1:
            text = text[:-2] + '…'
        else:
            break
    x = (x0 + x1 - left - right + 1) / 2
    if align == 'left':
        x = x0 - left
    elif align == 'right':
        x = x1 - right
    y = (y0 + y1 - top - bottom + 1) / 2
    draw.text((x, y), text, font=font(size, family), fill=color)


def score_symbol(draw, center: tuple[float, float], size: float, par: int | None, score: int | None,
                 foreground: str, under: str, over: str, family: str = 'sans', text_scale: float = 1):
    """Both the marker and glyph use one center, also for double-digit scores."""
    cx, cy = center
    size = max(2, size)
    half = size / 2
    inset = max(1, size * .08)
    stroke = max(1, round(size * .045))
    delta = score - par if score is not None and par is not None else 0
    bounds = (cx - half, cy - half, cx + half, cy + half)
    if delta < 0:
        draw.ellipse(bounds, outline=under, width=stroke)
        if delta <= -2:
            draw.ellipse((bounds[0] + inset, bounds[1] + inset, bounds[2] - inset, bounds[3] - inset), outline=under, width=stroke)
    elif delta > 0:
        draw.rectangle(bounds, outline=over, width=stroke)
        if delta >= 2:
            draw.rectangle((bounds[0] + inset, bounds[1] + inset, bounds[2] - inset, bounds[3] - inset), outline=over, width=stroke)
    text_box = (cx - half * .70, cy - half * .70, cx + half * .70, cy + half * .70)
    centered_text(draw, text_box, score, size * .59 * text_scale, foreground, family)


class Canvas:
    def __init__(self, size: tuple[int, int], style: Style):
        self.w, self.h = size
        self.s = style
        self.image = Image.new('RGBA', size)
        self.draw = ImageDraw.Draw(self.image)
        self.fg, self.accent = style.color, style.accent
        self.bg = style.background
        light = is_light(self.bg)
        self.alt = mix(self.bg, '#000000' if light else '#ffffff', .06)
        self.deep = mix(self.bg, '#000000', .10 if light else .25)
        self.muted = mix(self.fg, self.bg, .28)
        self.line = mix(self.fg, self.bg, .83)
        self.over = '#b74246' if light else '#ff9f98'
        self.accent_ink = '#102632' if is_light(self.accent) else '#ffffff'

    def box(self, x0, y0, x1, y1) -> Box:
        return (x0 * self.w, y0 * self.h, x1 * self.w, y1 * self.h)

    def background(self, box: Box, color: str):
        if self.s.panel:
            self.draw.rectangle(box, fill=(*ImageColor.getrgb(color), round(self.s.opacity * 255)))

    def text(self, box: Box, value, size: float, color=None, align='center'):
        centered_text(self.draw, box, value, size, color or self.fg, self.s.font, align)

    def finish(self) -> Image.Image:
        if self.s.panel and self.s.radius:
            mask = Image.new('L', self.image.size)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, self.w - 1, self.h - 1), radius=min(self.s.radius, self.w / 4, self.h / 4), fill=255)
            self.image.putalpha(ImageChops.multiply(self.image.getchannel('A'), mask))
        if self.s.overlay_opacity != 1:
            self.image.putalpha(self.image.getchannel('A').point(lambda a: round(a * self.s.overlay_opacity)))
        return self.image


def _shot(c: Canvas, p: Project, overlay: Overlay):
    shot = next(s for s in p.shots if s.id == overlay.shot_id)
    hole = p.round.holes[shot.hole - 1]
    number = numbered_shots(p)[shot.id]
    k = min(c.w / 620, c.h / 254)
    text_scale = c.s.font_size / 24
    c.background(c.box(0, 0, 1, 1), c.bg)
    c.draw.rectangle(c.box(0, 0, 1, .018), fill=c.accent)
    c.background(c.box(.81, .018, 1, .29), c.accent)
    c.text(c.box(.035, .045, .775, .255), p.round.player or 'PLAYER', 31 * k * text_scale, align='left')
    c.text(c.box(.82, .035, .99, .115), 'TO PAR', 18 * k * text_scale, c.accent_ink)
    c.text(c.box(.82, .13, .99, .265), relative_text(score_before_hole(p,shot.hole)), 36 * k * text_scale, c.accent_ink)
    c.background(c.box(0, .29, 1, .70), c.alt)
    c.background(c.box(.78, .29, 1, .70), c.deep)
    for x in (.24, .78):
        c.draw.line((x * c.w, c.h * .32, x * c.w, c.h * .68), fill=c.line, width=max(1, round(k)))
    c.text(c.box(.035, .32, .21, .405), 'HOLE', 20 * k * text_scale, c.muted, 'left')
    c.text(c.box(.035, .42, .21, .59), f'{shot.hole:02d}', 42 * k * text_scale, align='left')
    c.text(c.box(.035, .605, .21, .695), f'PAR {show(hole.par)}', 22 * k * text_scale, c.muted, 'left')
    c.text(c.box(.28, .32, .74, .405), 'LEFT', 20 * k * text_scale, c.muted, 'left')
    left = f'{shot.remaining:g} YDS' if shot.remaining is not None else '— YDS'
    c.text(c.box(.28, .43, .74, .68), left, 43 * k * text_scale, align='left')
    c.text(c.box(.80, .32, .98, .405), 'SHOT', 20 * k * text_scale, c.accent)
    c.text(c.box(.80, .42, .98, .69), number, 62 * k * text_scale, c.accent)
    # Match the approved broadcast mockup: remaining distance is primary;
    # the lower strip pairs an enlarged club with the full hole yardage.
    c.draw.line((0, c.h * .70, c.w, c.h * .70), fill=c.line, width=max(1, round(k)))
    c.text(c.box(.035, .72, .48, .80), 'CLUB', 18 * k * text_scale, c.muted, 'left')
    c.text(c.box(.035, .82, .48, .935), shot.club.upper(), 28 * k * text_scale, align='left')
    c.text(c.box(.53, .72, .965, .80), 'TOTAL', 18 * k * text_scale, c.muted, 'right')
    c.text(c.box(.53, .82, .965, .935), f'{show(hole.yardage)} YDS', 28 * k * text_scale, align='right')
    if c.s.show_course:
        c.text(c.box(.035, .955, .965, .995), ' · '.join(s for s in (p.round.course, p.round.tee) if s), 10 * k, c.muted, 'left')


def _minimal(c: Canvas, p: Project, overlay: Overlay):
    shot = next(s for s in p.shots if s.id == overlay.shot_id)
    k = min(c.w / 620, c.h / 254) * c.s.font_size / 24
    c.background(c.box(0, 0, 1, 1), c.bg)
    c.draw.rectangle(c.box(0, 0, .009, 1), fill=c.accent)
    c.text(c.box(.04, .08, .96, .28), f'HOLE {shot.hole:02d} · SHOT {numbered_shots(p)[shot.id]}', 24 * k, c.accent, 'left')
    c.text(c.box(.04, .36, .96, .63), shot.club.upper(), 40 * k, align='left')
    distance = f'{shot.distance:g} YDS' if shot.distance is not None else '— YDS'
    c.text(c.box(.04, .73, .96, .92), distance, 28 * k, align='left')


def _scorecard(c: Canvas, p: Project, overlay: Overlay):
    snapshot = p.snapshots[overlay.snapshot_id]
    r = snapshot.scorecard_data
    sections = [r.holes[:9], r.holes[9:]] if overlay.type == 'full' else [r.holes[:9] if overlay.type == 'front' else r.holes[9:]]
    k = min(c.w / 688, c.h / (430 if len(sections) == 2 else 292))
    text_scale = c.s.font_size / 24
    c.background(c.box(0, 0, 1, 1), c.bg)
    c.draw.rectangle(c.box(0, 0, 1, .011), fill=c.accent)
    c.text(c.box(.035, .035, .78, .105), r.player or 'PLAYER', 26 * k * text_scale, align='left')
    if c.s.show_course:
        metadata = ' · '.join(s for s in (r.course, r.tee, f'COURSE PAR {r.course_par}' if r.course_par is not None else '', f'CR {r.rating:g}' if r.rating is not None else '', f'SLOPE {r.slope}' if r.slope is not None else '') if s)
        c.text(c.box(.035, .117, .78, .155), metadata, 11 * k, c.muted, 'left')
    c.text(c.box(.81, .035, .965, .065), 'TO PAR', 10 * k, c.muted, 'right')
    c.text(c.box(.81, .075, .965, .15), relative_text(snapshot.relative_to_par), 34 * k * text_scale, c.accent, 'right')
    top, end = .19 * c.h, .79 * c.h
    section_h = (end - top) / len(sections)
    label_w, total_w = c.w * .07, c.w * .085
    left, right = c.w * .035, c.w * .965
    cell_w = (right - left - label_w - total_w) / 9
    center_x = lambda index: left + label_w + cell_w * (index + .5)
    total_box = lambda ya, yb: (right - total_w, ya, right, yb)
    for section, items in enumerate(sections):
        y = top + section * section_h
        section_end = y + section_h
        row_y = [y + section_h * fraction for fraction in (.20, .40, .57, .73)]
        out = items[0].number == 1
        label = 'FRONT NINE' if out else 'BACK NINE'
        c.draw.line((left, y, right, y), fill=c.line, width=max(1, round(k)))
        c.text((left, y + section_h * .035, right, y + section_h * .15), label, 10 * k, c.muted, 'left')
        # Labels, pars, yards and score marks share exactly the same column centers.
        for index, hole in enumerate(items):
            cx = center_x(index)
            box = lambda ya, yb: (cx - cell_w * .45, ya, cx + cell_w * .45, yb)
            c.text(box(row_y[0], row_y[0] + section_h * .13), hole.number, 12 * k, c.accent if hole.status == 'current' else c.muted)
            c.text(box(row_y[1], row_y[1] + section_h * .12), hole.par, 13 * k, c.muted)
            c.text(box(row_y[2], row_y[2] + section_h * .12), hole.yardage, 10 * k, c.muted)
            cy = y + section_h * .865
            marker_size = min(cell_w * .74, section_h * .235)
            score_symbol(c.draw, (cx, cy), marker_size, hole.par, hole.score, c.fg, c.accent, c.over, c.s.font, text_scale)
        for label, ry, height in (('HOLE', row_y[0], .13), ('PAR', row_y[1], .12), ('YDS', row_y[2], .12), ('SCORE', row_y[3], .25)):
            c.text((left, ry, left + label_w * .9, min(section_end, ry + section_h * height)), label, 9 * k, c.muted, 'left')
        t = totals(items)
        c.text(total_box(row_y[0], row_y[0] + section_h * .13), 'OUT' if out else 'IN', 11 * k, c.accent)
        c.text(total_box(row_y[1], row_y[1] + section_h * .12), t['par'], 13 * k, c.muted)
        c.text(total_box(row_y[2], row_y[2] + section_h * .12), t['yardage'], 10 * k, c.muted)
        c.text(total_box(y + section_h * .75, y + section_h * .98), t['score'], 27 * k * text_scale)
    c.background(c.box(0, .81, 1, .94), c.deep)
    for i, (label, value) in enumerate((('OUT', snapshot.front_nine_score), ('IN', snapshot.back_nine_score), ('PLAYED PAR', snapshot.total_par))):
        x = .035 + i * .18
        c.text(c.box(x, .83, x + .15, .865), label, 10 * k, c.muted, 'left')
        c.text(c.box(x, .875, x + .10, .922), value, 22 * k * text_scale, align='left')
    c.text(c.box(.70, .84, .805, .91), 'TOTAL', 10 * k, c.muted, 'right')
    c.text(c.box(.82, .827, .965, .923), snapshot.total_score, 38 * k * text_scale, c.accent, 'right')
    if snapshot.completed_holes_count < 18:
        note = f'{snapshot.completed_holes_count}/18 COMPLETED'
        if snapshot.current_hole is not None:
            note += f' · CURRENT HOLE {snapshot.current_hole}'
        c.text(c.box(.035, .957, .965, .989), note, 9 * k, c.muted, 'left')
    else:
        for i, (score, label) in enumerate(((2, 'EAGLE'), (3, 'BIRDIE'), (4, 'PAR'), (5, 'BOGEY'), (6, 'DOUBLE'))):
            x = .045 + i * .19
            cy = c.h * .969
            score_symbol(c.draw, (c.w * (x + .012), cy), c.h * .033, 4, score, c.fg, c.accent, c.over, c.s.font)
            c.text(c.box(x + .036, .947, x + .175, .99), label, 8 * k, c.muted, 'left')


def panel(p: Project, overlay: Overlay) -> Image.Image:
    """One raster source for web/native preview and FFmpeg, preserving video aspect."""
    s = overlay.style
    aspect = p.video.width / p.video.height if p.video else 16 / 9
    logical_width = max(240, round(1080 * aspect))
    size = (max(1, round(s.width * logical_width)), max(1, round(s.height * 1080)))
    canvas = Canvas(size, s)
    if overlay.type == 'shot':
        _shot(canvas, p, overlay)
    elif overlay.type == 'minimal':
        _minimal(canvas, p, overlay)
    else:
        _scorecard(canvas, p, overlay)
    return canvas.finish()


def png(p: Project, overlay: Overlay) -> bytes:
    output = io.BytesIO()
    panel(p, overlay).save(output, format='PNG')
    return output.getvalue()
