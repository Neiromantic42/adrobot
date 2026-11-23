"""Пересчёт весов офферов в потоке. Чистая логика: без БД и без Keitaro."""
from typing import Iterable, Protocol

TOTAL = 100
# Состояния, в которых оффер не участвует в распределении (значения OfferState).
INACTIVE_STATES = {"pending_remove", "removed"}


class WeightError(ValueError):
    """Веса нельзя привести к корректному распределению."""


class HasWeight(Protocol):
    weight: int
    pinned: bool
    state: str


def recalculate(items: Iterable[HasWeight]) -> None:
    """Меняет item.weight на месте.

    - pending_remove / removed получают вес 0;
    - запиненные офферы сохраняют вес;
    - остаток (100 - сумма запиненных) делится поровну между остальными,
      лишние единицы раздаются по +1 первым в списке (3 оффера -> 34/33/33).
    """
    items = list(items)
    live = [i for i in items if i.state not in INACTIVE_STATES]
    pinned = [i for i in live if i.pinned]
    free = [i for i in live if not i.pinned]

    pinned_sum = sum(i.weight for i in pinned)
    if pinned_sum > TOTAL:
        raise WeightError(f"Сумма запиненных весов {pinned_sum} больше {TOTAL}")

    for i in items:
        if i.state in INACTIVE_STATES:
            i.weight = 0

    if not free:
        return  # все запинены (или оффера нет): распределять нечего

    base, extra = divmod(TOTAL - pinned_sum, len(free))
    for idx, i in enumerate(free):
        i.weight = base + (1 if idx < extra else 0)