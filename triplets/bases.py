import typing as t
from hashlib import shake_128

Entity = str
Ordinal = str | int

T = t.TypeVar("T")
TOrdinal = t.TypeVar("TOrdinal", bound=Ordinal)

Fact = tuple[str, str, TOrdinal]

Context = dict[str, Ordinal]


def pluck_values(
    contexts: t.Sequence[Context], name: str, data_type: t.Type[T]
) -> set[T]:
    return {
        value
        for ctx in contexts
        if isinstance((value := ctx.get(name)), data_type)
    }


def storage_hash(text: str):
    """Returns a 32 chars string hash"""
    return shake_128(text.encode()).hexdigest(16)
