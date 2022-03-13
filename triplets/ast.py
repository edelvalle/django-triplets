import typing as t
from dataclasses import dataclass, replace

from . import ast_untyped as untyped
from .ast_untyped import Context, Ordinal, OrdinalType

VarTypes = dict[str, OrdinalType]


def type_name(ty: type) -> str:
    return getattr(ty, "__name__", str(ty))


def pluck_values(
    contexts: t.Iterable[Context],
    name: str,
) -> set[Ordinal] | None:
    values: set[Ordinal] = set()
    for ctx in contexts:
        if (value := ctx.get(name)) is None:
            return None
        else:
            values.add(value)
    return values


@dataclass(slots=True)
class Attr:
    name: str
    data_type: type[Ordinal]
    cardinality: t.Literal["one", "many"]

    @staticmethod
    def as_dict(*attrs: "Attr") -> "AttrDict":
        return {a.name: a for a in attrs}


AttrDict = dict[str, Attr]


# Internally typed for library use


@dataclass(slots=True)
class In:
    name: str
    values: set[Ordinal]
    data_type: type[Ordinal]

    def __repr__(self) -> str:
        return f"?{self.name}: {self.data_type.__name__} in {self.values}"

    def substitute(
        self, contexts: t.Iterable[Context]
    ) -> t.Union["In", Ordinal]:
        values = pluck_values(contexts, self.name)
        if values is None:
            # no values found means that the variable still not defined
            return self
        else:
            values.intersection_update(self.values)
            # just one value found means that this is now an Ordinal
            if len(values) == 1:
                # one found this is an Ordinal
                return values.pop()
            else:
                # return the subset found
                return replace(self, values=values)


@dataclass(slots=True)
class Var:
    name: str
    data_type: type[Ordinal]

    def __repr__(self) -> str:
        return f"?{self.name}: {self.data_type.__name__}"

    def substitute(
        self, contexts: t.Iterable[Context]
    ) -> t.Union[In, "Var", Ordinal]:
        if (values := pluck_values(contexts, self.name)) is None:
            # no values found means that the variable still not defined
            return self
        elif len(values) == 1:
            # just one value found means that this is now an Ordinal
            return values.pop()
        else:
            # a few values found means this is an In expression
            return In(self.name, values, self.data_type)


@dataclass(slots=True)
class Any:
    data_type: type[Ordinal]

    def __repr__(self) -> str:
        return f"?: {self.data_type.__name__}"


def all_are(values: set[t.Any], ty: type[object]) -> bool:
    return all(isinstance(v, ty) for v in values)


class Expression:
    T = In | Var | Ordinal


class LookUpExpression:
    T = Any | Expression.T

    @classmethod
    def from_entity_expression(cls, exp: untyped.EntityExpression) -> T:
        match exp:
            case str():
                return exp
            case untyped.In(name, values):
                if all_are(values, str):
                    return In(name, values, str)
                else:
                    raise TypeError(
                        f"Found entity values that are not str: {values}"
                    )
            case untyped.Var(name):
                return Var(name, str)
            case untyped.AnyType():
                return Any(str)

    @classmethod
    def from_value_expression(
        cls,
        exp: untyped.ValueExpression,
        attr_name: str,
        attributes: AttrDict,
    ) -> T:
        match exp:
            case str(value) | int(value):
                return value
            case untyped.Var(name):
                return Var(name, attributes[attr_name].data_type)
            case untyped.AnyType():
                return Any(attributes[attr_name].data_type)
            case untyped.In(name, values):
                return In(name, values, attributes[attr_name].data_type)

    @classmethod
    def ordinal_type(cls, self: T) -> type[Ordinal]:
        match self:
            case (In(_, _, data_type) | Var(_, data_type) | Any(data_type)):
                return data_type
            case int():
                return int
            case str():
                return str

    @classmethod
    def weight(cls, self: T) -> int:
        match self:
            case int() | str():
                return 0
            case In(_, values):
                # if has no values will produce no results,
                # so should be executed first
                return 1 if values else -100
            case Var():
                return 3
            case Any():
                return 7

    @classmethod
    def var_name(cls, self: T) -> str | None:
        match self:
            case In(name) | Var(name):
                return name
            case Any() | int() | str():
                return None

    @classmethod
    def matches(cls, self: T, value: Ordinal) -> t.Optional[Context]:
        """Returns the micro solution of matching an TypedExpression over a value.

        Returning None means that there was no match
        """
        match self:
            case str(ordinal_value) | int(ordinal_value):
                return {} if ordinal_value == value else None
            case In(name, values):
                return {name: value} if value in values else None
            case Var(name):
                return {name: value}
            case Any():
                return {}

    @classmethod
    def substitute(cls, self: T, contexts: t.Sequence[Context]) -> T:
        match self:
            case str() | int() | Any():
                return self
            case In() | Var():
                return self.substitute(contexts)
