import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop


def _make_kit(root, files):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_identical_trees_hash_equal(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    files = {"index.html": "<h1>hi</h1>", "css/style.css": "body{}"}
    _make_kit(a, files)
    _make_kit(b, files)
    assert workshop._kit_tree_hash(a) == workshop._kit_tree_hash(b)


def test_content_change_changes_hash(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    _make_kit(a, {"index.html": "<h1>hi</h1>"})
    _make_kit(b, {"index.html": "<h1>bye</h1>"})
    assert workshop._kit_tree_hash(a) != workshop._kit_tree_hash(b)


def test_added_file_changes_hash(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    _make_kit(a, {"index.html": "x"})
    _make_kit(b, {"index.html": "x", "extra.js": "y"})
    assert workshop._kit_tree_hash(a) != workshop._kit_tree_hash(b)
