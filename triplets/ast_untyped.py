import typing as t
from dataclasses import dataclass

Entity = str
Ordinal = str | int
OrdinalType = t.Type[Ordinal]
OrdinalTypes = (str, int)

Fact = tuple[str, str, Ordinal]
Context = dict[str, Ordinal]


@dataclass(slots=True)
class Var:
    name: str


@dataclass(slots=True)
class In:
    name: str
    value: set[Ordinal]


class AnyType:
    ...


Any = AnyType()


EntityExpression = AnyType | Var | In | str
ValueExpression = AnyType | Var | In | Ordinal

ClauseTuple = tuple[EntityExpression, str, ValueExpression]
PredicateTuples = t.Sequence[ClauseTuple]
