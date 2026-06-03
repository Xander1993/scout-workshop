import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop


def test_index_resolves_by_both_uuid_and_slug(tmp_path, monkeypatch):
    d = tmp_path / "references" / "awwwards" / "989723a6-studio-namma"
    d.mkdir(parents=True)
    (d / "note.md").write_text(
        "---\nid: 81cdf982-bd0e-56c9-ac2b-10de879eec4e\ntitle: Studio Namma\n---\n\n# X\n",
        encoding="utf-8")
    (d / "screenshot.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(workshop, "VAULT_DIR", tmp_path)
    index = workshop.build_vault_index()
    assert "81cdf982-bd0e-56c9-ac2b-10de879eec4e" in index   # legacy UUID key
    assert "989723a6-studio-namma" in index                  # NEW slug key (what anchors use)
    assert index["989723a6-studio-namma"][0].name == "note.md"
