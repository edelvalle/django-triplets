import typing as t
from dataclasses import dataclass, field, replace
from functools import cached_property
from hashlib import shake_128
from itertools import chain

from .ast import AttrDict, LookUpExpression, Ordinal, VarTypes
from .ast_untyped import ClauseTuple, Context, Fact, PredicateTuples
from .result import Err, Ok


def storage_hash(text: str):
    """Returns a 32 chars string hash"""
    return shake_128(text.encode()).hexdigest(16)


@dataclass(slots=True)
class Solution:
    context: Context
    derived_from: set[Fact]

    def __hash__(self) -> int:
        return hash(
            (frozenset(self.context.items()), frozenset(self.derived_from))
        )

    def merge(
        self,
        solutions: t.Iterable["Solution"],
    ) -> t.Iterable["Solution"]:
        for solution in solutions:
            # two solutions can merge when:
            # - we don't share the same facts in `derived_from`
            # - we can merge our contexts without override
            #   (meaning that their union is commutative)
            if (
                not self.derived_from
                or not self.derived_from.issubset(solution.derived_from)
            ) and (context := (self.context | solution.context)) == (
                solution.context | self.context
            ):
                yield Solution(
                    context=context,
                    derived_from=self.derived_from | solution.derived_from,
                )


@dataclass(frozen=True)
class Clause:
    entity: LookUpExpression.T
    attr: str
    value: LookUpExpression.T

    @classmethod
    def from_tuple(
        cls: type["Clause"],
        clause: ClauseTuple,
        attributes: AttrDict,
    ) -> "Clause":
        entity, attr, value = clause
        return cls(
            LookUpExpression.from_entity_expression(entity),
            attr,
            LookUpExpression.from_value_expression(value, attr, attributes),
        )

    def __repr__(self) -> str:
        return f"({self.entity}, {self.attr}, {self.value})"

    def substitute_using(self, contexts: list[Context]):
        """Replaces variables in this predicate with their values form the
        context
        """
        # This is an optimization
        if not contexts:
            return self

        return replace(
            self,
            entity=LookUpExpression.substitute(self.entity, contexts),
            value=LookUpExpression.substitute(self.value, contexts),
        )

    def __lt__(self, other: "Clause") -> bool:
        """This is here for the sorting protocol and query optimization"""
        return self.sorting_key < other.sorting_key

    @cached_property
    def sorting_key(self) -> int:
        """The more defined (literal values) this clause has, the lower
        the sorting number will be. So it gets priority when performing queries.
        """
        return LookUpExpression.weight(self.entity) + LookUpExpression.weight(
            self.value
        )

    @property
    def variable_types(self) -> VarTypes.MergeResult:
        return VarTypes.merge(
            [
                LookUpExpression.variable_types(self.entity),
                LookUpExpression.variable_types(self.value),
            ]
        )

    @property
    def as_fact(self) -> t.Optional[Fact]:
        if isinstance(self.entity, str) and isinstance(self.value, Ordinal):
            return (self.entity, self.attr, self.value)
        else:
            return None

    def matches(self, fact: Fact) -> t.Optional[Solution]:
        entity, attr, value = fact
        if self.attr != attr:
            return None
        if (
            entity_match := LookUpExpression.matches(self.entity, entity)
        ) is None:
            return None
        if (value_match := LookUpExpression.matches(self.value, value)) is None:
            return None
        return Solution(entity_match | value_match, {fact})


@dataclass(slots=True, init=False)
class Predicate(t.Iterable[Clause]):
    clauses: list[Clause]
    variables_types: VarTypes.T

    @classmethod
    def from_tuples(
        cls: type["Predicate"],
        attributes: AttrDict,
        predicate: PredicateTuples,
    ) -> "Predicate":
        return cls(
            [Clause.from_tuple(clause, attributes) for clause in predicate]
        )

    def __init__(
        self, clauses: list[Clause], variables_types: VarTypes.T | None = None
    ):
        self.clauses = clauses
        if variables_types is None:
            match VarTypes.merge(clause.variable_types for clause in self):
                case Ok(v_types):
                    self.variables_types = v_types
                case Err(mismatches):
                    VarTypes.raise_error(
                        mismatches,
                        f"Type mismatch in Predicate {self}, "
                        f"these variables have different types:",
                    )
        else:
            self.variables_types = variables_types

    def __repr__(self) -> str:
        return str(self.clauses)

    def optimized_by(self, contexts: list[Context]) -> list[Clause]:
        return list(sorted(self.substitute(contexts)))

    def substitute(self, contexts: list[Context]) -> t.Iterable[Clause]:
        return (clause.substitute_using(contexts) for clause in self)

    def evaluate(self, context: Context) -> t.Iterable[Fact]:
        for clause in self.substitute([context]):
            if (fact := clause.as_fact) is not None:
                yield fact

    def matches(self, fact: Fact) -> t.Iterable[Solution]:
        return (
            solution
            for clause in self
            if (solution := clause.matches(fact)) is not None
        )

    def __iter__(self) -> t.Iterator[Clause]:
        return iter(self.clauses)

    def __bool__(self) -> bool:
        return bool(self.clauses)


LookUpFunction = t.Callable[[Clause], t.Iterable[Fact]]


@dataclass(slots=True)
class Query:
    predicate: Predicate
    solutions: list[Solution] = field(
        default_factory=lambda: [Solution({}, set())]
    )

    @classmethod
    def from_tuples(
        cls: type["Query"],
        attributes: AttrDict,
        predicate: PredicateTuples,
    ) -> "Query":
        return cls(Predicate.from_tuples(attributes, predicate))

    @property
    def optimized_predicate(self) -> list[Clause]:
        return self.predicate.optimized_by([s.context for s in self.solutions])

    def solve(self, lookup: LookUpFunction) -> t.List[Solution]:
        if self.predicate and self.solutions:
            clause, *predicate = self.optimized_predicate
            predicate_solutions = [
                match
                for fact in lookup(clause)
                if (match := clause.matches(fact)) is not None
            ]
            next_query = Query(
                Predicate(predicate),
                solutions=list(
                    chain(
                        *[
                            solution.merge(predicate_solutions)
                            for solution in self.solutions
                        ]
                    )
                ),
            )
            return next_query.solve(lookup)
        else:
            return self.solutions


# @dataclass(slots=True)
# class Conclusions:
#     Function = t.Callable[..., t.Iterable[Fact]]

#     conclusions: Predicate | Function

#     @classmethod
#     def from_tuples(
#         cls: type["Conclusions"],
#         attributes: AttrDict,
#         predicate: PredicateTuples | Function,
#     ) -> "Conclusions":
#         if callable(predicate):
#             return cls(predicate)
#         else:
#             return cls(Predicate.from_tuples(attributes, predicate))

#     def __repr__(self) -> str:
#         if callable(self.conclusions):
#             return f"f{inspect.signature(self.conclusions)}"
#         else:
#             return str(self.conclusions)

#     @property
#     def has_any_type(self) -> bool:
#         if isinstance(self.conclusions, Predicate):
#             return any(
#                 isinstance(c.entity, Any) or isinstance(c.value, Any)
#                 for c in self.conclusions.clauses
#             )
#         else:
#             return False

#     def evaluate(self, context: Context) -> t.Iterable[Fact]:
#         if isinstance(self.conclusions, Predicate):
#             for clause in self.conclusions.substitute([context]):
#                 if (fact := clause.as_fact) is not None:
#                     yield fact
#         else:
#             yield from self.conclusions(**context)

#     @property
#     def variable_types(
#         self,
#     ) -> t.Iterable[tuple[str, t.Optional[type[Ordinal]]]]:
#         if isinstance(self.conclusions, Predicate):
#             yield from self.conclusions.variable_types.items()
#         else:
#             params = inspect.signature(self.conclusions).parameters.values()
#             for param in params:
#                 if param.kind not in (
#                     inspect.Parameter.VAR_POSITIONAL,
#                     inspect.Parameter.VAR_KEYWORD,
#                 ):
#                     param_type = (
#                         param.annotation
#                         if param.annotation in OrdinalTypes
#                         else None
#                     )
#                     yield param.name, param_type


@dataclass(init=False)
class Rule:
    predicate: Predicate
    implies: Predicate
    _context: Context = field(default_factory=dict)
    _variable_types: VarTypes.T = field(default_factory=dict)

    def __init__(
        self,
        predicate: Predicate,
        implies: Predicate,
        _context: Context | None = None,
        _variable_types: VarTypes.T | None = None,
    ):
        self.predicate = predicate
        self.implies = implies
        self._context = _context or {}
        if _variable_types is None:
            if any(
                var_name.startswith("*")
                for var_name in self.implies.variables_types
            ):
                raise TypeError(f"{self}, implications can't have Any on them")

            if missing_variables := set(self.implies.variables_types) - set(
                self.predicate.variables_types
            ):
                raise TypeError(
                    f"{self}, is missing these variables in the predicate: "
                    f"{missing_variables}"
                )

            match VarTypes.merge(
                [
                    Ok(self.predicate.variables_types),
                    Ok(self.implies.variables_types),
                ]
            ):
                case Ok(var_types):
                    self._variable_types = var_types
                case Err(mismatches):
                    VarTypes.raise_error(
                        mismatches, f"Type mismatch in {self}:"
                    )
        else:
            self._variable_types = _variable_types

    @cached_property
    def id(self) -> str:
        """This is an 32 chars long string Unique ID to this rule predicate and
        conclusions, so it can be stored in a database and help to identify
        facts generated by this rule.
        """
        return storage_hash(self.__repr__())

    def __repr__(self) -> str:
        return f"Rule: {self.predicate} => {self.implies}"

    def matches(self, fact: Fact) -> t.Iterable["Rule"]:
        """If the `fact` matches this rule this function returns a rule
        that you can run `Rule.run` on to return the derived facts
        """
        for match in self.predicate.matches(fact):
            predicate = self.predicate.substitute([match.context])
            yield replace(
                self,
                predicate=Predicate(list(predicate)),
                implies=self.implies,
                _variable_types=self._variable_types,
                _context=self._context | match.context,
            )

    def run(
        self,
        lookup: LookUpFunction,
    ) -> t.Iterable[tuple[Fact, set[Fact]]]:
        for solution in Query(self.predicate).solve(lookup):
            for fact in self.implies.evaluate(self._context | solution.context):
                yield (fact, solution.derived_from)


class RuleProtocol(t.Protocol):
    predicate: PredicateTuples
    implies: PredicateTuples


def compile_rules(attributes: AttrDict, *rules: RuleProtocol) -> list[Rule]:
    return [
        Rule(
            Predicate.from_tuples(attributes, r.predicate),
            Predicate.from_tuples(attributes, r.implies),
        )
        for r in rules
    ]


InferredFacts = t.Iterable[tuple[Fact, str, set[Fact]]]


def run_rules_matching(
    facts: t.Iterable[Fact],
    rules: t.Sequence[Rule],
    lookup: LookUpFunction,
) -> InferredFacts:
    matching_rules_and_original_ids = [
        (matching_rule, rule.id)
        for fact in facts
        for rule in rules
        for matching_rule in rule.matches(fact)
    ]
    return _run_rules(matching_rules_and_original_ids, lookup)


def refresh_rules(
    rules: t.Sequence[Rule],
    lookup: LookUpFunction,
) -> InferredFacts:
    return _run_rules(
        ((rule, rule.id) for rule in rules),
        lookup,
    )


def _run_rules(
    rules_and_original_ids: t.Iterable[tuple[Rule, str]],
    lookup: LookUpFunction,
) -> InferredFacts:
    for rule, original_rule_id in rules_and_original_ids:
        for fact, bases in rule.run(lookup):
            yield fact, original_rule_id, bases
