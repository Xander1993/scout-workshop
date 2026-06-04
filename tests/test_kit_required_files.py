import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop


def test_required_files_per_kit_type():
    es = workshop.KIT_REQUIRED_FILES_BY_KIT_TYPE["editorial-studio"]
    sp = workshop.KIT_REQUIRED_FILES_BY_KIT_TYPE["single-product"]
    assert "index.html" in es and "work.html" in es and "contact.html" in es
    assert "index.html" in sp and "work.html" not in sp          # single-product is one page
    assert "assets/css/style.css" in es and "assets/css/style.css" in sp
    assert "image-prompts.json" in es and "image-prompts.json" in sp
