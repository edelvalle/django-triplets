import typing as t
from dataclasses import dataclass

T = t.TypeVar("T")
TOk = t.TypeVar("TOk")
TErr = t.TypeVar("TErr")


@dataclass(slots=True)
class Ok(t.Generic[T]):
    value: T


@dataclass(slots=True)
class Err(t.Generic[T]):
    value: T


Result = Ok[TOk] | Err[TErr]
