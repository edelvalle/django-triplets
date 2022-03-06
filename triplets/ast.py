import typing as t
from dataclasses import dataclass

from .bases import Context, Ordinal, TOrdinal, pluck_values

# Untyped for user interface


@dataclass(slots=True)
class Attr:
    name: str
    data_type: type[Ordinal]
    cardinality: t.Literal["one", "many"]


AttrDict = dict[str, Attr]


@dataclass(slots=True)
class Var:
    name: str


class AnyType:
    ...


Any = AnyType()

# Internally typed for library use


@dataclass(slots=True)
class TypedIn(t.Generic[TOrdinal]):
    name: str
    values: set[TOrdinal]
    data_type: t.Type[TOrdinal]


@dataclass(slots=True)
class TypedVar(t.Generic[TOrdinal]):
    name: str
    data_type: t.Type[TOrdinal]


@dataclass(slots=True)
class TypedAny(t.Generic[TOrdinal]):
    data_type: t.Type[TOrdinal]


EntityExpression = AnyType | Var | str
ValueExpression = AnyType | Var | Ordinal
TypedExpression: t.TypeAlias = (
    TypedAny[TOrdinal] | TypedVar[TOrdinal] | TypedIn[TOrdinal] | TOrdinal
)


def typed_from_entity(exp: EntityExpression) -> TypedExpression[str]:
    match exp:
        case str():
            return exp
        case AnyType():
            return TypedAny(str)
        case Var(name):
            return TypedVar(name, str)


def typed_from_value(
    exp: ValueExpression, attribute: Attr
) -> TypedExpression[Ordinal]:
    match exp:
        case Var(name):
            return TypedVar(name, attribute.data_type)
        case AnyType():
            return TypedAny(attribute.data_type)
        case _:
            if isinstance(exp, attribute.data_type):
                return exp
            else:
                raise TypeError(
                    f"Attribute {attribute.name} type is "
                    f"{attribute.data_type}, can't have value: {exp}"
                )


def expression_type(exp: TypedExpression[TOrdinal]) -> t.Type[Ordinal]:
    match exp:
        case (
            TypedIn(_, _, data_type)
            | TypedVar(_, data_type)
            | TypedAny(data_type)
        ):
            return data_type
        case int():
            return int
        case str():
            return str


def expression_weight(exp: TypedExpression[TOrdinal]) -> int:
    match exp:
        case int() | str():
            return 0
        case TypedIn():
            return 1
        case TypedVar():
            return 3
        case TypedAny():
            return 7


def expression_var_name(exp: TypedExpression[TOrdinal]) -> str | None:
    match exp:
        case TypedIn(name) | TypedVar(name):
            return name
        case TypedAny() | int() | str():
            return None


def expression_matches(
    expression: TypedExpression[TOrdinal], value: TOrdinal
) -> t.Optional[Context]:
    """Returns the micro solution of matching an TypedExpression over a value.

    Returning None means that there was no match
    """
    match expression:
        case str(ordinal_value) | int(ordinal_value):
            return {} if ordinal_value == value else None
        case TypedIn(name, values):
            return {name: value} if value in values else None
        case TypedVar(name):
            return {name: value}
        case TypedAny():
            return {}


def substitute_using(
    expression: TypedExpression[TOrdinal], contexts: list[Context]
) -> TypedExpression[TOrdinal]:
    match expression:
        case str() | int() | TypedAny():
            return expression
        case TypedIn(name, desired_values, data_type):
            values = pluck_values(contexts, name, data_type)
            if not values:
                return expression
            else:
                # contrain to the desired values
                values = values.intersection(desired_values)
                if len(values) == 1:
                    return values.pop()
                else:
                    return TypedIn(name, values, data_type)
        case TypedVar(name, data_type):
            values = pluck_values(contexts, name, data_type)
            if not values:
                # no values found means that the variable still not defined
                return expression
            elif len(values) == 1:
                # just one value found means that this is now a literal
                return values.pop()
            else:
                # a few values found means this is an TypedIn expression
                return TypedIn(expression.name, values, data_type)
