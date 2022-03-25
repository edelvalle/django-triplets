import operator
import typing as t
from dataclasses import dataclass

Entity = str
Ordinal = str | int | float
OrdinalType = t.Type[Ordinal]
OrdinalTypes = (str, int, float)

Fact = tuple[str, str, Ordinal]
Context = dict[str, Ordinal]


@dataclass(slots=True)
class Var:
    name: str

    def __gt__(self, other: t.Union["Var", Ordinal]) -> "Comparison":
        return Comparison(">", self, other)

    def __ge__(self, other: t.Union["Var", Ordinal]) -> "Comparison":
        return Comparison(">=", self, other)

    def __lt__(self, other: t.Union["Var", Ordinal]) -> "Comparison":
        return Comparison("<", self, other)

    def __le__(self, other: t.Union["Var", Ordinal]) -> "Comparison":
        return Comparison("<=", self, other)


@dataclass(slots=True)
class In:
    name: str
    value: set[Ordinal]


ComparisonOperator = (
    t.Literal["<"] | t.Literal["<="] | t.Literal[">="] | t.Literal[">"]
)
operators: dict[ComparisonOperator, t.Callable[[Ordinal, Ordinal], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">=": operator.ge,
    ">": operator.gt,
}
reverse_operator: dict[ComparisonOperator, ComparisonOperator] = {
    "<": ">=",
    "<=": ">",
    ">": "<=",
    ">=": "<",
}


@dataclass(slots=True)
class Comparison:
    operator: ComparisonOperator
    left: Var
    right: Var | Ordinal

    def __and__(self, other: "BooleanExpression") -> "And":
        return And(self, other)


@dataclass(slots=True)
class And:
    left: "BooleanExpression"
    right: "BooleanExpression"

    def __and__(self, other: "BooleanExpression") -> "And":
        return And(self, other)


BooleanExpression = And | Comparison | In


class AnyType:
    ...


Any = AnyType()

EntityExpression = AnyType | Var | BooleanExpression | str
ValueExpression = AnyType | Var | BooleanExpression | Ordinal

ClauseTuple = tuple[EntityExpression, str, ValueExpression]
PredicateTuples = t.Sequence[ClauseTuple]
