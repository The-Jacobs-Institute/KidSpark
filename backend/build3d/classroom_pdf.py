"""Format-specific classroom PDFs from editable lesson-bundle Markdown."""
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image, Flowable

BLUE = colors.HexColor("#4095cc")
INK = colors.HexColor("#26313a")
IMAGE_PREFIXES = ("Final built reference image:", "Placement views:", "Image:")


def _markup(text):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(text))


def _sections(text):
    title, sections = "Storytime Inventing", []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("<!--"):
            continue
        if line.startswith("# "):
            title = line[2:]
        elif line.startswith("## "):
            sections.append((line[3:], []))
        elif line:
            if not sections:
                sections.append(("", []))
            sections[-1][1].append(line)
    return title, sections


def _styles(size=10):
    return {
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=size, leading=size * 1.34, textColor=INK, spaceAfter=5),
        "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=size, leading=size * 1.34, textColor=INK, leftIndent=12, firstLineIndent=-10, spaceAfter=5),
        "heading": ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=size + 5, leading=size + 8, textColor=BLUE, spaceBefore=10, spaceAfter=6, keepWithNext=True),
    }


def _body(lines, styles, width, image_height=170):
    from PIL import Image as PILImage
    items = []
    for line in lines:
        prefix = next((p for p in IMAGE_PREFIXES if line.startswith(p)), None)
        if prefix:
            path = Path(line[len(prefix):].strip())
            if not path.is_file():
                items.append(Paragraph("Build image unavailable", styles["body"]))
                continue
            with PILImage.open(path) as source:
                w, h = source.size
            scale = min(width / max(w, 1), image_height / max(h, 1))
            picture = Image(str(path), width=w * scale, height=h * scale)
            picture.hAlign = "CENTER"
            items.extend([picture, Spacer(1, 6)])
        elif line.startswith("###"):
            items.append(Paragraph(_markup(line.lstrip("# ")), styles["heading"]))
        elif line.startswith("- "):
            items.append(Paragraph("&bull; " + _markup(line[2:]), styles["bullet"]))
        else:
            items.append(Paragraph(_markup(line), styles["body"]))
    return items


def _height(items, width):
    return sum(item.wrap(width, 10000)[1] + item.getSpaceBefore() + item.getSpaceAfter() for item in items)


def _section(heading, lines, styles, width, image_height=170):
    heading_style = ParagraphStyle("section", parent=styles["heading"])
    if "Explore" in heading:
        heading_style.textColor = colors.HexColor("#ce642a")
    elif "Invent" in heading and not "Storytime" in heading:
        heading_style.textColor = colors.HexColor("#6b9b36")
    return [Paragraph(_markup(heading), heading_style), *_body(lines, styles, width, image_height)]


def _activity_groups(sections):
    """Tolerate equivalent generated headings without discarding their content."""
    groups = {}
    for heading, lines in sections:
        canonical = re.sub(r"^Step\s+0?([123])\s*[:\-]\s*", r"Step 0\1 - ", heading, flags=re.I)
        if canonical.lower() in {"step 02 - learn and explore", "step 02 - learn & explore"}:
            canonical = "Step 02 - Learn & Explore"
        if canonical.lower() == "reflection":
            canonical = "Reflection Questions"
        groups.setdefault(canonical, []).extend(lines)
    return groups


def _columns(left, right, widths):
    table = Table([[left, right]], colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


class ResponseLines(Flowable):
    def __init__(self, width, height=66):
        super().__init__()
        self.width, self.height = width, height

    def draw(self):
        self.canv.setStrokeColor(colors.HexColor("#c8d9e2"))
        for y in range(10, int(self.height), 20):
            self.canv.line(0, y, self.width, y)


def write_classroom_pdf(path: Path) -> Path:
    kind = path.stem
    text = path.read_text(encoding="utf-8")
    title, sections = _sections(text)
    slide, activity = kind == "slide_companion", kind == "activity_guide"
    size = (720, 405) if slide else ((792, 612) if activity else (612, 792))
    label = {"lesson_plan": "TEACHER LESSON PLAN", "activity_guide": "ACTIVITY GUIDE", "slide_companion": "SLIDE COMPANION"}[kind]
    width = size[0] - 64
    grade = next((line[7:] for _, lines in sections for line in lines if line.startswith("Grade: ")), "")
    if activity:
        grade = next((h.split(" - ", 1)[1] for h, _ in sections if h.startswith("Activity Guide - ")), "")
        title = next((line.split("Build focus:", 1)[1].strip().replace("**", "") for _, lines in sections for line in lines if line.startswith("Build focus:")), title)
    display_title = re.sub(r"\s+Slide Companion$", "", title)
    preview = "UNVALIDATED LAYOUT PREVIEW" in text or "LOCAL VALIDATION FIXTURE" in text
    footer = "UNVALIDATED LAYOUT PREVIEW - NOT CLASSROOM INSTRUCTIONS" if preview else "KidSpark AI | Teacher review required"

    def page(canvas, doc):
        w, h = size
        canvas.saveState()
        canvas.setFillColor(BLUE)
        canvas.rect(0, 0 if slide else h - 83, w, h if slide else 83, fill=1, stroke=0)
        if slide:
            canvas.setFillColor(colors.white)
            canvas.roundRect(20, 28, w - 40, h - 106, 8, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(32, h - 17, "STORYTIME INVENTING")
        name_style = ParagraphStyle("banner", fontName="Helvetica-Bold", fontSize=19, leading=21, textColor=colors.white)
        name = Paragraph(_markup(display_title), name_style)
        while name.wrap(w - 64, 100)[1] > 43 and name_style.fontSize > 11:
            name_style.fontSize -= 1
            name_style.leading -= 1
            name = Paragraph(_markup(display_title), name_style)
        _, nh = name.wrap(w - 64, 100)
        name.drawOn(canvas, 32, h - 22 - nh)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(32, h - 75, " | ".join(filter(None, [grade.upper(), label])))
        canvas.setFillColor(colors.white if slide else colors.HexColor("#607582"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(32, 14, footer)
        canvas.drawRightString(w - 32, 14, str(doc.page))
        canvas.restoreState()

    story = []
    if slide:
        reference = next((line for _, lines in sections for line in lines if line.startswith("Final built reference image:")), None)
        # Oversized content may continue onto another page, never clip or disappear.
        for index, (heading, lines) in enumerate(sections):
            if index:
                story.append(PageBreak())
            heading = re.sub(r"^Slide \d+\s*-\s*", "", heading)
            pictures = [line for line in lines if line.startswith(IMAGE_PREFIXES)]
            words = [line for line in lines if not line.startswith(IMAGE_PREFIXES)]
            if not pictures and reference and heading in {"Parts And Their Jobs", "Plan Before You Build"}:
                pictures = [reference]
            story.append(Paragraph(_markup(heading), _styles(15)["heading"]))
            if pictures:
                for font_size in (16, 15, 14, 13):
                    styles = _styles(font_size)
                    left = _body(words, styles, 310)
                    if _height(left, 310) <= 208:
                        break
                right = _body(pictures, styles, 306, 200 / max(1, len(pictures)))
                pair = _columns(left, right, [330, width - 330])
                story.extend([pair] if pair.wrap(width, 1000)[1] <= 220 else left + right)
            else:
                story.extend(_body(words, _styles(21), width - 12))
    elif activity:
        styles, groups = _styles(12), _activity_groups(sections)
        left, right = [], []
        for name in ("Step 01 - Read", "Vocabulary", "Sound Awareness"):
            lines = groups.pop(name, [])
            if lines:
                left.extend(_section(name, lines, styles, 230))
        explore = groups.pop("Step 02 - Learn & Explore", [])
        example = next((line for line in groups.get("Example Build", []) if line.startswith("Final built reference image:")), None)
        if explore:
            right.extend(_section("Step 02 - Learn & Explore", [], styles, 458))
        if example:
            parts = _body(explore, styles, 205)
            model = _body([example], styles, 213, 205)
            nested = _columns(parts, model, [225, 233])
            right.extend([nested] if nested.wrap(458, 1000)[1] < 260 else parts + model)
        else:
            right.extend(_body(explore, styles, 458))
        invent = groups.pop("Step 03 - Invent", [])
        if invent:
            right.extend(_section("Step 03 - Invent", invent, styles, 458))
        right.extend(_section("My design idea", ["What will you build? Draw your idea and label its important parts."], styles, 458))
        right.append(ResponseLines(438, 66))
        pair = _columns(left, right, [250, width - 250])
        story.extend([pair] if pair.wrap(width, 1000)[1] < 460 else left + right)
        example_lines = groups.pop("Example Build", [])
        left = _section("Example Build", example_lines, styles, 410, 185) if example_lines else []
        right = []
        for name in ("Real-World Connection", "Reflection Questions"):
            lines = groups.pop(name, [])
            if lines:
                right.extend(_section(name, lines, styles, 278))
        if left or right:
            story.append(PageBreak())
            if right:
                right.append(ResponseLines(260))
            if left and right:
                pair = _columns(left, right, [430, width - 430])
                story.extend([pair] if pair.wrap(width, 1000)[1] < 460 else left + right)
            else:
                story.extend(left + right)
        for heading, lines in groups.items():
            if not heading.startswith("Activity Guide - "):
                story.extend(_section(heading, lines, styles, width))
    else:
        styles = _styles()
        order = ["Storytime Inventing Teacher Lesson Plan", "Materials", "Build Preview", "Teacher Overview", "Learning Objectives", "Vocabulary And Literacy Focus", "Anticipatory Set", "Step 01: Read", "Step 02: Learn & Explore", "Step 03: Invent", "Closure & Reflection Questions", "Plan For All Learners", "Standards And Framework Alignment", "SEL Focus"]
        sections.sort(key=lambda s: order.index(s[0]) if s[0] in order else len(order))
        for heading, lines in sections:
            if heading == "Storytime Inventing Teacher Lesson Plan":
                heading = "Activity Details"
            pictures = [line for line in lines if line.startswith(IMAGE_PREFIXES)]
            words = [line for line in lines if not line.startswith(IMAGE_PREFIXES)]
            story.extend(_section(heading, words, styles, width))
            if pictures:
                cells = [_body([line], styles, width / len(pictures) - 16, 172) for line in pictures]
                story.append(Table([cells], colWidths=[width / len(cells)] * len(cells)))
    pdf = path.with_suffix(".pdf")
    document = SimpleDocTemplate(str(pdf), pagesize=size, leftMargin=32, rightMargin=32, topMargin=90 if slide else 96, bottomMargin=34, title=display_title, author="KidSpark AI")
    document.build(story, onFirstPage=page, onLaterPages=page)
    return pdf
