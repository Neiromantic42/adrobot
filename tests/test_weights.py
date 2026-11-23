from dataclasses import dataclass

import pytest

from app.services.weights import WeightError, recalculate


@dataclass
class Item:
    weight: int = 0
    pinned: bool = False
    state: str = "active"


def weights(items):
    return [i.weight for i in items]


def test_three_free_offers_sum_to_100():
    items = [Item(), Item(), Item()]
    recalculate(items)
    assert weights(items) == [34, 33, 33]


def test_four_offers_get_25_each():
    items = [Item() for _ in range(4)]
    recalculate(items)
    assert weights(items) == [25, 25, 25, 25]


def test_single_offer_gets_100():
    items = [Item()]
    recalculate(items)
    assert weights(items) == [100]


def test_pinned_weight_is_kept():
    items = [Item(weight=25, pinned=True), Item(), Item()]
    recalculate(items)
    assert weights(items) == [25, 38, 37]


def test_pending_remove_gets_zero_and_others_share():
    items = [Item(), Item(), Item(state="pending_remove")]
    recalculate(items)
    assert weights(items) == [50, 50, 0]


def test_removed_gets_zero():
    items = [Item(weight=33, state="removed"), Item(), Item()]
    recalculate(items)
    assert weights(items) == [0, 50, 50]


def test_pending_add_takes_part_in_distribution():
    items = [Item(), Item(), Item(state="pending_add")]
    recalculate(items)
    assert sum(weights(items)) == 100


def test_video_scenario_pin_then_bring_back():
    # 4 оффера, один запинен на 25, остальные считаются заново
    items = [Item(weight=25, pinned=True), Item(), Item(), Item(state="pending_add")]
    recalculate(items)
    assert weights(items) == [25, 25, 25, 25]


def test_pinned_sum_over_100_raises():
    items = [Item(weight=70, pinned=True), Item(weight=50, pinned=True), Item()]
    with pytest.raises(WeightError):
        recalculate(items)


def test_all_pinned_nothing_changes():
    items = [Item(weight=30, pinned=True), Item(weight=40, pinned=True)]
    recalculate(items)
    assert weights(items) == [30, 40]


def test_pinned_100_leaves_free_with_zero():
    items = [Item(weight=100, pinned=True), Item()]
    recalculate(items)
    assert weights(items) == [100, 0]


def test_no_live_offers_does_not_fail():
    items = [Item(weight=50, state="removed")]
    recalculate(items)
    assert weights(items) == [0]


def test_empty_list():
    recalculate([])


@pytest.mark.parametrize("n", range(1, 21))
def test_sum_is_always_100_for_free_offers(n):
    items = [Item() for _ in range(n)]
    recalculate(items)
    assert sum(weights(items)) == 100
    assert max(weights(items)) - min(weights(items)) <= 1


@pytest.mark.parametrize("pinned_weight", [0, 1, 10, 33, 99])
def test_sum_is_100_with_one_pinned(pinned_weight):
    items = [Item(weight=pinned_weight, pinned=True)] + [Item() for _ in range(3)]
    recalculate(items)
    assert sum(weights(items)) == 100