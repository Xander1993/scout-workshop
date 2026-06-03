import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import migrate_listing_frames as mlf


def test_retags_idempotently_without_qdrant(tmp_path):
    d = tmp_path / "references" / "awwwards" / "989723a6-studio-namma"
    d.mkdir(parents=True)
    (d / "note.md").write_text(
        "---\nid: abc\ntitle: Studio Namma\nreference_type: studio_site\nqdrant_point_id: abc\n---\n\n# X\n",
        encoding="utf-8")
    assert mlf.retag(tmp_path, sync_qdrant=False) == 1
    text = (d / "note.md").read_text()
    assert "reference_type: listing_frame" in text
    assert "original_reference_type: studio_site" in text
    assert mlf.retag(tmp_path, sync_qdrant=False) == 0   # idempotent
