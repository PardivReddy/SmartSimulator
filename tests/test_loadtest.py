import pytest

from smartdialer.loadtest import run_load_test


def test_load_test_reserves_each_borrower_at_most_once():
    result = run_load_test(agents=12, borrowers=9, workers=6, seed=17)
    assert result["result"] == "PASS"
    assert result["expected_reservations"] == 9
    assert result["reservations"] == 9
    assert result["duplicate_borrower_reservations"] == 0
    assert result["worker_errors"] == 0


def test_load_test_rejects_nonpositive_parameters():
    with pytest.raises(ValueError, match="must be positive"):
        run_load_test(agents=0)
