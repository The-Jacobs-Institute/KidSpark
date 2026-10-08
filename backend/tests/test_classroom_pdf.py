from pathlib import Path

import pytest
from PIL import Image

from build3d.classroom_pdf import write_classroom_pdf
from build3d.pipeline import _activity_vocabulary_definition

import fitz


def test_slide_keeps_instruction_and_image_on_one_widescreen_page(tmp_path):
    picture = tmp_path / "step.png"
    Image.new("RGB", (900, 700), "blue").save(picture)
    path = tmp_path / "slide_companion.md"
    path.write_text(f"# Test Lesson\n## Slide 1 - Build Step 1\n- Find the pieces and compare their position with the picture.\n- Test the connection with your partner.\nImage: {picture}\n", encoding="utf-8")
    with fitz.open(write_classroom_pdf(path)) as pdf:
        assert len(pdf) == 1
        assert tuple(pdf[0].rect)[2:] == (720, 405)
        assert len(pdf[0].get_images()) == 1
        assert "Test the connection" in pdf[0].get_text()


def test_activity_is_landscape_and_missing_image_does_not_leak_path(tmp_path):
    path = tmp_path / "activity_guide.md"
    path.write_text("# A lesson\n## Activity Guide - 1st Grade\nBuild focus: Plane\n## Step 01 - Read\nListen to the story.\n## Example Build\nImage: /private/missing.png\n## Reflection Questions\n- What changed?\n", encoding="utf-8")
    with fitz.open(write_classroom_pdf(path)) as pdf:
        assert tuple(pdf[0].rect)[2:] == (792, 612)
        text = " ".join(page.get_text() for page in pdf)
        assert "Build image unavailable" in text
        assert "/private" not in text
        assert "What changed?" in text


def test_long_lesson_continues_without_losing_final_text(tmp_path):
    path = tmp_path / "lesson_plan.md"
    lines = [f"Paragraph {i}: " + "Students explain their design to a partner. " * 5 for i in range(45)]
    path.write_text("# My Lesson\n## Teacher Overview\n" + "\n".join(lines) + "\n## SEL Focus\nFINAL SENTINEL", encoding="utf-8")
    with fitz.open(write_classroom_pdf(path)) as pdf:
        text = " ".join(page.get_text() for page in pdf)
        assert "FINAL SENTINEL" in text
        assert all(f"Paragraph {i}:" in text for i in range(45))
        assert all(len(page.get_text().split()) > 12 for page in pdf)


def test_vocabulary_definition_matches_selected_word():
    assert "person" in _activity_vocabulary_definition([], "Inventor")
    assert _activity_vocabulary_definition([{"term": "Test", "definition": "Try an idea."}], "Test") == "Try an idea."
    assert "machine" not in _activity_vocabulary_definition([], "Redesign")


def test_activity_heading_variants_and_static_build(tmp_path):
    path = tmp_path / "activity_guide.md"
    path.write_text("# Bridge\n## Step 01: Read\nRead together.\n## Step 02 - Learn and Explore\nCOMPARE SUPPORTS\n## Step 03 - Invent\nBuild a static bridge.\n", encoding="utf-8")
    with fitz.open(write_classroom_pdf(path)) as pdf:
        assert len(pdf) == 1
        text = " ".join(page.get_text() for page in pdf)
        assert "COMPARE SUPPORTS" in text
        assert "Vocabulary" not in text
        assert "Sound Awareness" not in text
        assert "part that moves" not in text
        assert "BrickSmart" not in text
