import typing as t
from dataclasses import dataclass

Entity = str
Ordinal = str | int

T = t.TypeVar("T")

Fact = tuple[str, str, Ordinal]

Context = dict[str, Ordinal]


def pluck_values(
    contexts: t.Sequence[Context], name: str, data_type: type[T]
) -> set[T]:
    return {
        value
        for ctx in contexts
        if isinstance((value := ctx.get(name)), data_type)
    }


@dataclass(slots=True)
class Attr:
    name: str
    data_type: type[Ordinal]
    cardinality: t.Literal["one", "many"]

    @staticmethod
    def as_dict(*attrs: "Attr") -> "AttrDict":
        return {a.name: a for a in attrs}


AttrDict = dict[str, Attr]


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

# Internally typed for library use


@dataclass(slots=True)
class TypedIn:
    name: str
    values: set[Ordinal]
    data_type: t.Type[Ordinal]


@dataclass(slots=True)
class TypedVar:
    name: str
    data_type: t.Type[Ordinal]


@dataclass(slots=True)
class TypedAny:
    data_type: t.Type[Ordinal]


EntityExpression = AnyType | Var | In | str
ValueExpression = AnyType | Var | In | Ordinal
TypedExpression = TypedAny | TypedVar | TypedIn | Ordinal


def all_are(values: set[t.Any], ty: t.Type[object]) -> bool:
    return all(isinstance(v, ty) for v in values)


def typed_from_entity(exp: EntityExpression) -> TypedExpression:
    match exp:
        case str():
            return exp
        case In(name, values):
            assert all_are(
                values, str
            ), f"Found values that are not string here: {values}"
            return TypedIn(name, values, str)
        case Var(name):
            return TypedVar(name, str)
        case AnyType():
            return TypedAny(str)


def typed_from_value(exp: ValueExpression, attribute: Attr) -> TypedExpression:
    match exp:
        case Var(name):
            return TypedVar(name, attribute.data_type)
        case AnyType():
            return TypedAny(attribute.data_type)
        case In(name, values):
            return TypedIn(name, values, attribute.data_type)
        case str(value) | int(value):
            return value


def expression_type(exp: TypedExpression) -> type[Ordinal]:
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


def expression_weight(exp: TypedExpression) -> int:
    match exp:
        case int() | str():
            return 0
        case TypedIn():
            return 1
        case TypedVar():
            return 3
        case TypedAny():
            return 7


def expression_var_name(exp: TypedExpression) -> str | None:
    match exp:
        case TypedIn(name) | TypedVar(name):
            return name
        case TypedAny() | int() | str():
            return None


def expression_matches(
    expression: TypedExpression, value: Ordinal
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
    expression: TypedExpression,
    contexts: list[Context],
) -> TypedExpression:
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
