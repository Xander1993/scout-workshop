import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop


def test_passed_kit_returns_zero():
    assert workshop._oneshot_rc({"passed": True}) == 0


def test_flagged_kit_returns_nonzero():
    # a below-bar kit must NOT read as a ship, so register_weekly keeps trying
    assert workshop._oneshot_rc({"passed": False}) != 0


def test_no_kit_returns_nonzero():
    assert workshop._oneshot_rc(None) != 0
