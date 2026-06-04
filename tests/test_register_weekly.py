import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop
import register_schedule


def _patch_common(monkeypatch, tmp_path):
    # never touch the real /var/lock flock or Telegram in these unit tests
    monkeypatch.setattr(workshop, "acquire_lock", lambda *a, **k: open(tmp_path / "lk", "w"))
    monkeypatch.setattr(workshop, "_alert_register_result", lambda *a, **k: None)
    monkeypatch.setattr(workshop, "_send_telegram_text_raw", lambda *a, **k: None)
    monkeypatch.setattr(register_schedule, "active_pairs", lambda: [("x", "y")] * 6)


def test_stops_on_first_ship(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(register_schedule, "next_pair",
                        lambda *a, **k: ("sun-baked", "editorial-studio"))
    monkeypatch.setattr(workshop, "run_awwwards_oneshot",
                        lambda s, k: (calls.append((s, k)), 0)[1])
    assert workshop.run_register_weekly() == 0
    assert len(calls) == 1                     # stopped after the first ship


def test_advances_on_fail_then_ships(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    pairs = iter([("a", "editorial-studio"), ("b", "single-product"), ("c", "editorial-studio")])
    monkeypatch.setattr(register_schedule, "next_pair", lambda *a, **k: next(pairs))
    rcs = iter([1, 0, 0])                       # first pair fails, second ships
    calls = []
    monkeypatch.setattr(workshop, "run_awwwards_oneshot",
                        lambda s, k: (calls.append((s, k)), next(rcs))[1])
    assert workshop.run_register_weekly() == 0
    assert len(calls) == 2                      # advanced once, then shipped


def test_wall_clock_budget_breaks_loop(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(workshop, "REGISTER_WALL_BUDGET_S", 0)   # budget already spent
    monkeypatch.setattr(register_schedule, "next_pair", lambda *a, **k: ("x", "y"))
    called = []
    monkeypatch.setattr(workshop, "run_awwwards_oneshot",
                        lambda s, k: called.append(1) or 1)
    assert workshop.run_register_weekly() == 1   # total failure
    assert called == []                          # budget break → never launched a pair


def test_empty_active_set_returns_1(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(register_schedule, "active_pairs", lambda: [])
    assert workshop.run_register_weekly() == 1
