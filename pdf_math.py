"""Vector PDF layout for the bounded MathML produced by manuscript.py.

No TeX engine, evaluation, font files, external tools or content execution.
Coordinates are in points relative to the mathematical baseline.
"""
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET

import pymupdf


@dataclass
class Formula:
    width: float
    ascent: float
    descent: float
    glyphs: list = field(default_factory=list)
    strokes: list = field(default_factory=list)

    @property
    def height(self):
        return self.ascent + self.descent

    def add(self, other, x=0, y=0):
        self.glyphs.extend((gx+x, gy+y, text, size, font) for gx, gy, text, size, font in other.glyphs)
        self.strokes.extend(([(px+x, py+y) for px, py in points], width) for points, width in other.strokes)
        self.ascent = max(self.ascent, other.ascent-y)
        self.descent = max(self.descent, other.descent+y)

    def draw(self, page, rectangle):
        # Story leaves its page transformation active. Isolate that graphics
        # state before adding normal top-left-coordinate PDF content.
        page.wrap_contents()
        scale = min(rectangle.width / self.width, rectangle.height / self.height)
        baseline = rectangle.y0 + self.ascent * scale
        writer = pymupdf.TextWriter(page.rect)
        for x, y, text, size, font in self.glyphs:
            writer.append((rectangle.x0+x*scale, baseline+y*scale), text, font=font, fontsize=size*scale)
        writer.write_text(page, color=(0.13, 0.13, 0.13))
        shape = page.new_shape()
        for points, width in self.strokes:
            shape.draw_polyline([(rectangle.x0+x*scale, baseline+y*scale) for x, y in points])
            shape.finish(width=width*scale, color=(0.13, 0.13, 0.13), closePath=False)
        shape.commit()


class _Layout:
    def __init__(self):
        # These fonts are provided by the existing PyMuPDF runtime. TextWriter
        # retains Unicode text, including supported Greek/operator glyphs.
        self.fonts = {variant: pymupdf.Font(name) for variant, name in
                      [('normal', 'tiro'), ('italic', 'tiit'), ('bold', 'tibo')]}
        self.fallback = pymupdf.Font('cjk')

    def text(self, value, size, variant):
        result = Formula(0, 0, 0)
        for char in value:
            font = self.fonts[variant]
            if not font.has_glyph(ord(char)):
                font = self.fallback
            if not font.has_glyph(ord(char)):
                raise ValueError('PDF math font cannot represent a formula glyph.')
            glyph = Formula(font.text_length(char, fontsize=size), font.ascender*size,
                            -font.descender*size, [(0, 0, char, size, font)])
            result.add(glyph, result.width)
            result.width += glyph.width
        return result

    def node(self, node, size, variant=None):
        kind = node.tag.rsplit('}', 1)[-1]
        if kind in {'math', 'mrow', 'mstyle'}:
            variant = node.get('mathvariant', variant)
            result = Formula(0, 0, 0)
            for child in node:
                content = self.node(child, size, variant)
                result.add(content, result.width)
                result.width += content.width
            return result
        if kind == 'mspace':
            return Formula(size*.2, 0, 0)
        if kind in {'mi', 'mn', 'mo'}:
            text = node.text or ''
            style = node.get('mathvariant') or variant or ('italic' if kind == 'mi' else 'normal')
            result = self.text(text, size, style)
            if kind == 'mo' and text not in '()[]{}|.,;!':
                padded = Formula(result.width+size*.3, 0, 0)
                padded.add(result, size*.15)
                return padded
            return result
        if kind == 'mfrac':
            numerator, denominator = (self.node(child, size*.9, variant) for child in node)
            width = max(numerator.width, denominator.width)+size*.36
            result = Formula(width, 0, 0)
            axis = -size*.25
            result.add(numerator, (width-numerator.width)/2, axis-size*.2-numerator.descent)
            result.add(denominator, (width-denominator.width)/2, axis+size*.2+denominator.ascent)
            result.strokes.append(([(0, axis), (width, axis)], max(.4, size*.045)))
            return result
        if kind in {'msup', 'msub', 'msubsup'}:
            base = self.node(node[0], size, variant)
            result = Formula(base.width, 0, 0)
            result.add(base)
            lower = self.node(node[1], size*.68, variant) if kind in {'msub', 'msubsup'} else None
            upper = self.node(node[2 if kind == 'msubsup' else 1], size*.68, variant) if kind in {'msup', 'msubsup'} else None
            upper_y = -max(size*.6, base.ascent-upper.ascent*.55) if upper else 0
            lower_y = max(size*.35, base.descent+lower.ascent*.35) if lower else 0
            if lower and upper:
                lower_y = max(lower_y, upper_y+upper.descent+lower.ascent+size*.12)
            for script, y in [(upper, upper_y), (lower, lower_y)]:
                if script:
                    result.add(script, base.width+size*.08, y)
            result.width += size*.08+max(script.width for script in (lower, upper) if script)
            return result
        if kind in {'msqrt', 'mroot'}:
            content = self.node(node[0], size, variant)
            degree = self.node(node[1], size*.55, variant) if kind == 'mroot' else None
            degree_width = max(0, degree.width-size*.2) if degree else 0
            left = degree_width+size*.72
            roof = -content.ascent-size*.12
            bottom = max(size*.12, content.descent)
            result = Formula(left+content.width+size*.12, -roof+size*.05, bottom)
            result.add(content, left)
            result.strokes.append(([(degree_width, -size*.16), (degree_width+size*.17, -size*.27),
                                    (degree_width+size*.34, bottom), (degree_width+size*.63, roof),
                                    (result.width, roof)], max(.4, size*.045)))
            if degree:
                result.add(degree, 0, roof+degree.ascent*.6)
            return result
        raise ValueError('Formula is outside the bounded PDF layout subset.')


def layout_math(mathml, fontsize=11):
    """Input is exclusively the escaped parser-produced math element."""
    result = _Layout().node(ET.fromstring(mathml), fontsize)
    if result.width <= 0 or result.height <= 0:
        raise ValueError('Empty PDF formula layout.')
    return result
