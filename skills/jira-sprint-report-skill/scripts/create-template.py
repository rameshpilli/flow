#!/usr/bin/env python3
"""
Creates a BASELINE_TEMPLATE.pptx with branded master slides.
This template can then be used with generate-report.py --template
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.util import Emu
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import nsmap

def rgb_color(r, g, b):
    """Helper to create RGB color."""
    from pptx.dml.color import RGBColor
    return RGBColor(r, g, b)

# Template colors (matching the uploaded image)
BG_COLOR = rgb_color(0xf5, 0xf5, 0xf0)  # Light cream/beige
ACCENT_COLOR = rgb_color(0xa5, 0xa5, 0x90)  # Subtle greenish-gray for lines
DARK_COLOR = rgb_color(0x1e, 0x29, 0x3b)
FOOTER_TEXT = "XYZ – PIP ALPHA"

SLIDE_WIDTH = Inches(10)
SLIDE_HEIGHT = Inches(5.625)


def create_baseline_template(output_path):
    """Create a branded PowerPoint template."""
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    # Create a blank slide to establish the template
    # We'll use the blank layout (index 6 or last)
    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    # Background
    background = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_WIDTH, SLIDE_HEIGHT
    )
    background.fill.solid()
    background.fill.fore_color.rgb = BG_COLOR
    background.line.fill.background()

    # Geometric line pattern (similar to uploaded image)
    lines = [
        (0.5, 0.3, 4.0),
        (1.0, 0.6, 3.5),
        (0.3, 1.0, 5.0),
        (1.5, 0.9, 4.5),
        (0.8, 1.4, 3.0),
        (2.0, 0.4, 6.0),
        (0.4, 1.8, 4.0),
        (1.2, 1.2, 5.5),
        (3.0, 0.5, 4.0),
        (2.5, 1.0, 3.5),
        (0.6, 2.2, 5.0),
        (1.8, 1.6, 4.5),
        (3.5, 0.8, 3.0),
        (0.3, 2.8, 4.0),
        (2.2, 2.0, 3.5),
        (4.0, 1.2, 4.0),
        (1.0, 3.2, 5.0),
        (3.0, 2.5, 3.0),
        (0.5, 3.8, 4.5),
        (2.5, 3.0, 4.0),
    ]

    for x, y, length in lines:
        # Horizontal lines
        line = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(x), Inches(y),
            Inches(length), Pt(0.75)
        )
        line.fill.solid()
        line.fill.fore_color.rgb = ACCENT_COLOR
        line.line.fill.background()

    # Some diagonal-ish lines (angled boxes)
    diagonals = [
        (0.5, 0.5, 2.5, 1.5),
        (2.0, 1.0, 3.0, 2.0),
        (1.0, 2.0, 2.0, 3.0),
        (3.5, 1.5, 4.5, 2.5),
        (0.8, 3.5, 2.8, 4.5),
        (4.0, 2.0, 5.5, 3.5),
    ]

    for x1, y1, x2, y2 in diagonals:
        # Create angled lines using connectors (simplified as thin rectangles)
        connector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(x1), Inches(y1),
            Inches(x2), Inches(y2)
        )
        connector.line.color.rgb = ACCENT_COLOR
        connector.line.width = Pt(0.5)

    # Footer branding
    footer = slide.shapes.add_textbox(
        Inches(7.5), Inches(5.2), Inches(2.3), Inches(0.3)
    )
    tf = footer.text_frame
    p = tf.paragraphs[0]
    p.text = FOOTER_TEXT
    p.font.size = Pt(10)
    p.font.color.rgb = DARK_COLOR
    p.font.name = "Arial"
    p.alignment = PP_ALIGN.RIGHT

    # Save
    prs.save(output_path)
    print(f"✅ Template created: {output_path}")


if __name__ == '__main__':
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else 'BASELINE_TEMPLATE.pptx'
    create_baseline_template(output)
