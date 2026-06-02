"""Состояние дневной сессии ученика (в памяти процесса).

Хранит текущий набор заданий и индекс активного задания. Для продакшена это
состояние можно вынести в БД/redis; для одного процесса достаточно памяти.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.models import Task


@dataclass
class DailySession:
    chat_id: int
    tasks: list[Task]
    index: int = 0
    # выбранные номера для заданий с inline-тогглами (по task_id)
    selected_numbers: dict[int, set[int]] = field(default_factory=dict)
    day_scores: list[float] = field(default_factory=list)

    @property
    def current(self) -> Task | None:
        return self.tasks[self.index] if self.index < len(self.tasks) else None

    @property
    def finished(self) -> bool:
        return self.index >= len(self.tasks)

    def advance(self, score: float) -> None:
        self.day_scores.append(score)
        self.index += 1

    def toggle(self, task_id: int, number: int) -> set[int]:
        s = self.selected_numbers.setdefault(task_id, set())
        if number in s:
            s.discard(number)
        else:
            s.add(number)
        return s


class SessionStore:
    """Реестр активных сессий по chat_id."""

    def __init__(self) -> None:
        self._sessions: dict[int, DailySession] = {}

    def start(self, chat_id: int, tasks: list[Task]) -> DailySession:
        s = DailySession(chat_id=chat_id, tasks=tasks)
        self._sessions[chat_id] = s
        return s

    def get(self, chat_id: int) -> DailySession | None:
        return self._sessions.get(chat_id)

    def clear(self, chat_id: int) -> None:
        self._sessions.pop(chat_id, None)
