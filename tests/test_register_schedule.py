import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import register_schedule as rs


def test_active_pairs_excludes_vault_pending():
    pairs = rs.active_pairs()
    subs = {p[0] for p in pairs}
    assert "sun-baked" in subs and "warm-earth" in subs and "editorial-mid-century" in subs
    assert "acid-tech" not in subs and "cool-jewel" not in subs       # vault_pending
    kits = {p[1] for p in pairs}
    assert kits == {"editorial-studio", "single-product"}
    assert len(pairs) == 6                                            # 3 active × 2 kit-types


def test_next_pair_rotates_and_persists(tmp_path):
    sp = tmp_path / "q.json"
    seen = [rs.next_pair(sp) for _ in range(7)]
    pairs = rs.active_pairs()
    assert seen[0] == pairs[0] and seen[6] == pairs[0]               # wrapped after 6
    assert len(set(seen[:6])) == 6                                   # all distinct in one cycle
    assert sp.exists()


def test_next_pair_recovers_from_corrupt_state(tmp_path):
    sp = tmp_path / "q.json"
    sp.write_text("{ not json", encoding="utf-8")
    pair = rs.next_pair(sp)                                          # must not raise
    assert pair == rs.active_pairs()[0]
