import typing as t
from collections import defaultdict
from dataclasses import dataclass, field, replace
from uuid import uuid4

from . import ast_untyped as untyped
from .ast_untyped import Context, Ordinal, OrdinalType, reverse_operator
from .result import Err, Ok, Result


class VarTypes:
    T = dict[str, OrdinalType]
    Mismatches = defaultdict[str, set[OrdinalType]]
    MergeResult = Result[T, Mismatches]

    @staticmethod
    def merge(results: t.Iterable[MergeResult]) -> MergeResult:
        """Merges the variables types from `a` and `b`.
        This fails in case a variable from `a` has a different type in `b`.
        """
        final_result: VarTypes.T = {}
        final_mismatches: VarTypes.Mismatches = defaultdict(set)

        for result in results:
            match result:
                case Ok(var_types):
                    for name, var_type in var_types.items():
                        if (
                            r_type := final_result.get(name)
                        ) is None or r_type == var_type:
                            final_result[name] = var_type
                        else:
                            final_mismatches[name].update([r_type, var_type])
                case Err(mismatches):
                    for name, types in mismatches.items():
                        final_mismatches[name].update(types)

        return Err(final_mismatches) if final_mismatches else Ok(final_result)

    @staticmethod
    def raise_error(mismatches: Mismatches, msg: str):
        messages = [msg]
        for name, types in mismatches.items():
            messages.append(
                f"- {name}: " + ", ".join(type_name(t) for t in types)
            )
        raise TypeError("\n".join(messages))


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
    data_type: OrdinalType
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
    data_type: OrdinalType

    @classmethod
    def new_null(
        cls, data_type: OrdinalType, *, name: str | None = None
    ) -> "In":
        return In(name or str(uuid4()), set(), data_type)

    def __repr__(self) -> str:
        return f"?{self.name}: {self.data_type.__name__} in {self.values}"

    def __hash__(self) -> int:
        return hash((self.name, tuple(self.values), self.data_type))

    def substitute(
        self, contexts: t.Sequence[Context]
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
    data_type: OrdinalType

    @classmethod
    def new_hidden(cls, data_type: OrdinalType) -> "Var":
        return cls(str(uuid4()), data_type)

    def __repr__(self) -> str:
        return f"?{self.name}: {self.data_type.__name__}"

    def __hash__(self) -> int:
        return hash((self.name, self.data_type))

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


class ComparisionOperand:
    T = Var | Ordinal

    @classmethod
    def are_the_same_type(cls, left: T, right: T) -> bool:
        return cls.get_type(left) == cls.get_type(right)

    @classmethod
    def get_type(cls, self: T) -> OrdinalType:
        match self:
            case int():
                return int
            case str():
                return str
            case float():
                return float
            case Var(_, data_type):
                return data_type

    @classmethod
    def substitute(
        cls, self: T, contexts: t.Iterable[Context]
    ) -> Var | In | Ordinal:
        match self:
            case str() | int() | float():
                return self
            case Var():
                return self.substitute(contexts)


@dataclass(slots=True)
class Comparison:
    operator: untyped.ComparisonOperator
    left: ComparisionOperand.T
    right: ComparisionOperand.T

    def __repr__(self) -> str:
        return f"{self.left} {self.operator} {self.right}"

    def __hash__(self) -> int:
        return hash((self.operator, hash(self.left), hash(self.right)))

    @property
    def for_lookup(
        self,
    ) -> tuple[Var, untyped.ComparisonOperator, Ordinal]:
        left_is_ordinal = isinstance(self.left, Ordinal)
        right_is_ordinal = isinstance(self.right, Ordinal)
        if left_is_ordinal ^ right_is_ordinal:
            if left_is_ordinal:
                return (
                    t.cast(Var, self.right),
                    reverse_operator[self.operator],
                    t.cast(Ordinal, self.left),
                )
            else:
                return (
                    t.cast(Var, self.left),
                    self.operator,
                    t.cast(Ordinal, self.right),
                )
        else:
            raise RuntimeError(f"Comparision: {self} can't be looked up")

    def substitute(self, contexts: t.Sequence[Context]) -> "BooleanExpression":
        left = ComparisionOperand.substitute(self.left, contexts)
        right = ComparisionOperand.substitute(self.right, contexts)
        match left:
            case str() | int() | float():
                match right:
                    case int() | str() | float():
                        # 1 < 10 => 1 < x' < 10
                        hidden_var = Var.new_hidden(type(left))
                        return And(
                            replace(self, left=left, right=hidden_var),
                            replace(self, left=hidden_var, right=right),
                        )
                    case Var():
                        # 1 < x => 1 < x
                        return replace(self, left=left, right=right)
                    case In(_, values, data_type):
                        # 3 < x in {1, 2, 3, 4} => 3 < x' < max(x)
                        # 3 > x in {1, 2, 3, 4} => 3 > x' > min(x)
                        # 3 > x in Ø => x' in Ø
                        if values:
                            hidden_var = Var.new_hidden(data_type)
                            extreme = self._extreme(values, goes="right")
                            return And(
                                replace(self, left=left, right=hidden_var),
                                replace(self, left=hidden_var, right=extreme),
                            )
                        else:
                            return In.new_null(data_type)
            case Var(left_name):
                match right:
                    case str() | int() | float():
                        # x < 1 => x < 1
                        return replace(self, left=left, right=right)
                    case Var():
                        # x < y => x < y
                        return replace(self, left=left, right=right)
                    case In(_, values, data_type):
                        # x < y in {1, 2, 3} => x < max(y)
                        # x > y in {1, 2, 3} => x > min(y)
                        # x > y in Ø => x in Ø
                        if values:
                            extreme = self._extreme(values, goes="right")
                            return replace(self, left=left, right=extreme)
                        else:
                            return In.new_null(data_type, name=left_name)
            case In(_, values, data_type):
                match right:
                    case str() | int() | float():
                        # x in {1, 2, 3} < 2 => min(x) < x' < 2
                        # x in {1, 2, 3} > 2 => max(x) > x' > 2
                        # x in Ø > 2 => x' in Ø
                        if values:
                            hidden_var = Var.new_hidden(data_type)
                            extreme = self._extreme(values, goes="left")
                            return And(
                                replace(self, left=extreme, right=hidden_var),
                                replace(self, left=hidden_var, right=right),
                            )
                        else:
                            return In.new_null(data_type)

                    case Var(right_name):
                        # x in {1, 2, 3} < y => min(x) < y
                        # x in {1, 2, 3} > y => max(x) > min(y)
                        # x > y in Ø => x in Ø
                        if values:
                            extreme = self._extreme(values, goes="left")
                            return replace(self, left=extreme, right=right)
                        else:
                            return In.new_null(data_type, name=right_name)
                    case In(_, right_values, _):
                        # x in {1, 2, 3} < y in {2, 3, 4} => min(x) < 'x < max(y)
                        # x in {1, 2, 3} > y in {2, 3, 4} => max(x) > 'x > min(y)
                        # x in Ø || y in Ø => 'x in Ø
                        if values and right_values:
                            hidden_var = Var.new_hidden(data_type)
                            left_value = self._extreme(values, goes="left")
                            right_value = self._extreme(
                                right_values, goes="right"
                            )
                            return And(
                                replace(
                                    self, left=left_value, right=hidden_var
                                ),
                                replace(
                                    self, left=hidden_var, right=right_value
                                ),
                            )
                        else:
                            return In.new_null(data_type)

    def _extreme(
        self,
        values: set[Ordinal],
        *,
        goes: t.Union[t.Literal["left"], t.Literal["right"]],
    ) -> Ordinal:
        match self.operator:
            case "<" | "<=":
                return max(values) if goes == "right" else min(values)
            case ">" | ">=":
                return min(values) if goes == "right" else max(values)


@dataclass(slots=True)
class And:
    left: "BooleanExpression"
    right: "BooleanExpression"

    def __hash__(self) -> int:
        return hash((hash(self.left), hash(self.right)))

    def substitute(self, contexts: t.Sequence[Context]) -> "And":
        return replace(
            self,
            left=self.left.substitute(contexts),
            right=self.right.substitute(contexts),
        )


BooleanExpression = And | Comparison | In


@dataclass(slots=True)
class Any:
    data_type: OrdinalType
    internal_name: str = field(default_factory=lambda: f"*{uuid4()}")

    def __repr__(self) -> str:
        return f"?: {self.data_type.__name__}"

    def __hash__(self):
        return hash((self.internal_name, self.data_type))


def all_are(values: set[t.Any], ty: type[object]) -> bool:
    return all(isinstance(v, ty) for v in values)


class Expression:
    T = BooleanExpression | Var | Ordinal


class LookUpExpression:
    T = Any | Expression.T

    @classmethod
    def from_entity_expression(cls, exp: untyped.EntityExpression) -> T:
        match exp:
            case str():
                return exp
            case untyped.And(left, right):
                typed_left = t.cast(
                    BooleanExpression, cls.from_entity_expression(left)
                )
                typed_right = t.cast(
                    BooleanExpression, cls.from_entity_expression(right)
                )
                return And(typed_left, typed_right)
            case untyped.Comparison(operator, left, right):
                match right:
                    case str() | untyped.Var():
                        typed_left = t.cast(
                            ComparisionOperand.T,
                            cls.from_entity_expression(left),
                        )
                        typed_right = t.cast(
                            ComparisionOperand.T,
                            cls.from_entity_expression(right),
                        )
                        return Comparison(operator, typed_left, typed_right)
                    case int() | float():
                        raise TypeError(
                            f"Found entity comparision that are not a str: "
                            f"{right}"
                        )
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
            case str(value) | int(value) | float(value):
                return value
            case untyped.And(left, right):
                typed_left = t.cast(
                    BooleanExpression, cls.from_entity_expression(left)
                )
                typed_right = t.cast(
                    BooleanExpression, cls.from_entity_expression(right)
                )
                return And(typed_left, typed_right)
            case untyped.Comparison(operator, left, right):
                typed_left = t.cast(
                    ComparisionOperand.T,
                    cls.from_value_expression(left, attr_name, attributes),
                )
                typed_right = t.cast(
                    ComparisionOperand.T,
                    cls.from_value_expression(right, attr_name, attributes),
                )
                if not ComparisionOperand.are_the_same_type(
                    typed_left, typed_right
                ):
                    raise TypeError(
                        f"Can't compare two different types: "
                        f"{typed_left} {operator} {typed_right}"
                    )
                return Comparison(operator, typed_left, typed_right)
            case untyped.Var(name):
                return Var(name, attributes[attr_name].data_type)
            case untyped.AnyType():
                return Any(attributes[attr_name].data_type)
            case untyped.In(name, values):
                return In(name, values, attributes[attr_name].data_type)

    @classmethod
    def variable_types(cls, self: T) -> VarTypes.MergeResult:
        match self:
            case int() | str() | float():
                return Ok({})
            case (
                In(name, _, data_type)
                | Var(name, data_type)
                | Any(data_type, name)
            ):
                return Ok({name: data_type})
            case Comparison(_, left, right) | And(left, right):
                return VarTypes.merge(
                    [cls.variable_types(left), cls.variable_types(right)]
                )

    @classmethod
    def matches(cls, self: T, value: Ordinal) -> t.Iterable[Context]:
        """Returns the micro solution of matching an TypedExpression over a value.

        Returning None means that there was no match
        """
        match self:
            case str(ordinal_value) | int(ordinal_value) | float(ordinal_value):
                if ordinal_value == value:
                    yield {}

            case In(name, values):
                if value in values:
                    yield {name: value}

            case Var(name):
                yield {name: value}

            case Comparison(op, left, right):
                match left:
                    case Var(left_name):
                        match right:
                            case str() | int() | float():
                                if untyped.operators[op](value, right):
                                    yield {left_name: value}
                            case Var(right_name):
                                # matches both because we don't know for sure
                                yield {left_name: value}
                                yield {right_name: value}
                    case str() | int() | float():
                        match right:
                            case Var(right_name):
                                if untyped.operators[op](left, value):
                                    yield {right_name: value}
                            case str() | int() | float():
                                if untyped.operators[op](left, right):
                                    yield {}

            case And(left, right):
                for left_match in cls.matches(left, value):
                    for right_match in cls.matches(right, value):
                        yield left_match | right_match

            case Any():
                yield {}

    @classmethod
    def substitute(cls, self: T, contexts: t.Sequence[Context]) -> T:
        match self:
            case str() | int() | float() | Any():
                return self
            case In() | Var() | Comparison() | And():
                return self.substitute(contexts)
