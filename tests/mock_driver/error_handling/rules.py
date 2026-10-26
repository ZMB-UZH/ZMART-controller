from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    REFUSED_BY_LIMITS = "refused by limits"
    BAD_REQUEST = "bad request"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    UNKNOWN_READING = "unknown reading"
    UNCONFIRMED = "unconfirmed"
    CONNECTION_LOST = "connection lost"


class Action(Enum):
    RAISE = "raise"
    RETRY = "try again"
    RETURN_UNKNOWN = "return 'unknown'"
    NOT_CONFIRMED_YET = "count as not confirmed yet"
    SEND_AGAIN_THEN_GIVE_UP = "send again, then give up softly"
    NOT_APPLICABLE = "does not happen here"


@dataclass(frozen=True)
class Rule:
    get: Action
    set: Action
    error: type[Exception] | None


RULES: dict[Kind, Rule] = {
    Kind.REFUSED_BY_LIMITS: Rule(Action.NOT_APPLICABLE, Action.RAISE, ValueError),
    Kind.BAD_REQUEST: Rule(Action.RAISE, Action.RAISE, ValueError),
    Kind.TEMPORARY: Rule(Action.RETRY, Action.RETRY, RuntimeError),
    Kind.PERMANENT: Rule(Action.RAISE, Action.RAISE, RuntimeError),
    Kind.UNKNOWN_READING: Rule(Action.RETURN_UNKNOWN, Action.NOT_CONFIRMED_YET, None),
    Kind.UNCONFIRMED: Rule(Action.NOT_APPLICABLE, Action.SEND_AGAIN_THEN_GIVE_UP, None),
    Kind.CONNECTION_LOST: Rule(Action.RAISE, Action.RAISE, RuntimeError),
}
