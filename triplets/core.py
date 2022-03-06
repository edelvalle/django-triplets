import typing as t
from collections import defaultdict
from dataclasses import dataclass, field, replace
from functools import cached_property
from itertools import chain

from .ast import (
    AttrDict,
    EntityExpression,
    TypedExpression,
    ValueExpression,
    expression_matches,
    expression_type,
    expression_var_name,
    expression_weight,
    substitute_using,
    typed_from_entity,
    typed_from_value,
)
from .bases import Context, Fact, Ordinal, TOrdinal, storage_hash


@dataclass(slots=True)
class Solution:
    context: Context
    derived_from: set[Fact[Ordinal]]

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
class Clause(t.Generic[TOrdinal]):
    subject: TypedExpression[str]
    verb: str
    obj: TypedExpression[TOrdinal]

    def substitute_using(self, contexts: list[Context]):
        """Replaces variables in this predicate with their values form the
        context
        """
        # This is an optimization
        if not contexts:
            return self

        new_subject = substitute_using(self.subject, contexts)
        new_object = substitute_using(self.obj, contexts)
        return replace(self, subject=new_subject, object=new_object)

    def __lt__(self, other: "Clause[t.Any]") -> bool:
        """This is here for the sorting protocol and query optimization"""
        return self.sorting_key < other.sorting_key

    @cached_property
    def sorting_key(self) -> int:
        """The more defined (literal values) this clause has, the lower
        the sorting number will be. So it gets priority when performing queries.
        """
        return expression_weight(self.subject) + expression_weight(self.obj)

    @property
    def variable_types(self) -> defaultdict[str, set[t.Type[Ordinal]]]:
        variable_types: defaultdict[str, set[t.Type[Ordinal]]] = defaultdict(
            set
        )
        if name := expression_var_name(self.subject):
            variable_types[name].add(expression_type(self.subject))
        if name := expression_var_name(self.obj):
            variable_types[name].add(expression_type(self.obj))
        return variable_types

    @property
    def as_dict(self) -> dict[str, TypedExpression[Ordinal]]:
        return dict(self.__dict__)

    @property
    def as_fact(self) -> t.Optional[Fact[TOrdinal]]:
        if isinstance(self.subject, str) and isinstance(self.obj, Ordinal):
            return (self.subject, self.verb, self.obj)
        else:
            return None

    def matches(self, fact: Fact[TOrdinal]) -> t.Optional[Solution]:
        subject, verb, obj = fact
        if self.verb != verb:
            return None
        if (subject_match := expression_matches(self.subject, subject)) is None:
            return None
        if (obj_match := expression_matches(self.obj, obj)) is None:
            return None
        return Solution(subject_match | obj_match, {fact})


ClauseTuple = tuple[EntityExpression, str, ValueExpression]
PredicateTuples = t.Sequence[ClauseTuple]


@dataclass(slots=True)
class Predicate(t.Iterable[Clause[Ordinal]]):
    clauses: list[Clause[Ordinal]]

    @classmethod
    def from_tuples(
        cls: t.Type["Predicate"],
        predicate: PredicateTuples,
        attributes: AttrDict,
    ) -> "Predicate":
        return cls(
            [
                Clause(
                    typed_from_entity(entity),
                    attr,
                    typed_from_value(value, attributes[attr]),
                )
                for entity, attr, value in predicate
            ]
        )

    def __post_init__(self):
        # validate that the types of all variables are coherent
        # this will raise if
        self.variable_types

    def optimized_by(self, contexts: list[Context]) -> list[Clause[Ordinal]]:
        return list(sorted(self.substitute(contexts)))

    def substitute(
        self, contexts: list[Context]
    ) -> t.Iterable[Clause[Ordinal]]:
        return (clause.substitute_using(contexts) for clause in self)

    def matches(self, fact: Fact[Ordinal]) -> t.Iterable[Solution]:
        return (
            solution
            for clause in self
            if (solution := clause.matches(fact)) is not None
        )

    @property
    def variable_types(self) -> dict[str, t.Type[Ordinal]]:
        variable_types: defaultdict[str, set[t.Type[Ordinal]]] = defaultdict(
            set
        )
        for clause in self.clauses:
            for name, types in clause.variable_types.items():
                variable_types[name].update(types)

        result: dict[str, t.Type[Ordinal]] = {}
        for var_name, types in variable_types.items():
            if len(types) == 1:
                result[var_name] = types.pop()
            else:
                raise TypeError(
                    f"Variable {var_name} can't have more than one type: "
                    f"{list(types)}"
                )
        return result

    def __iter__(self) -> t.Iterator[Clause[Ordinal]]:
        return iter(self.clauses)

    def __bool__(self) -> bool:
        return bool(self.clauses)

    def __add__(self, other: "Predicate") -> "Predicate":
        return replace(self, clauses=self.clauses + other.clauses)


LookUpFunction = t.Callable[[Clause[TOrdinal]], t.Iterable[Fact[TOrdinal]]]


@dataclass(slots=True)
class Query:
    predicate: Predicate
    solutions: list[Solution] = field(
        default_factory=lambda: [Solution({}, set())]
    )

    @classmethod
    def from_tuples(
        cls: t.Type["Query"], predicate: PredicateTuples, attributes: AttrDict
    ) -> "Query":
        return cls(Predicate.from_tuples(predicate, attributes))

    @property
    def optimized_predicate(self) -> list[Clause[Ordinal]]:
        return self.predicate.optimized_by([s.context for s in self.solutions])

    def solve(self, lookup: LookUpFunction[TOrdinal]) -> t.List[Solution]:
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


@dataclass
class Rule:
    predicate: Predicate
    conclusions: Predicate
    validate_consistency: bool = field(default=True)

    @cached_property
    def id(self) -> str:
        """This is an 32 chars long string Unique ID to this rule predicate and
        conclusions, so it can be stored in a database and help to identify
        facts generated by this rule.
        """
        return storage_hash(self.__repr__())

    def __post_init__(self):
        # check the predicates can be merged type wise
        if self.validate_consistency:
            self.conclusions + self.predicate

            # check conclusions variables are satisfied by the predicate
            missing_variables = set(self.conclusions.variable_types) - set(
                self.predicate.variable_types
            )
            if missing_variables:
                raise TypeError(
                    f"{self} requires {missing_variables} in the predicate"
                )

    def matches(self, fact: Fact[Ordinal]) -> t.Iterable["Rule"]:
        """If the `fact` matches this rule this function returns a rule
        that you can run `Rule.run` on to return the derived facts
        """
        for match in self.predicate.matches(fact):
            predicate = self.predicate.substitute([match.context])
            conclusions = self.conclusions.substitute([match.context])
            yield replace(
                self,
                predicate=Predicate(list(predicate)),
                conclusions=Predicate(list(conclusions)),
                validate_consistency=False,
            )

    def run(
        self,
        lookup: LookUpFunction[Ordinal],
    ) -> t.Iterable[tuple[Fact[Ordinal], set[Fact[Ordinal]]]]:
        for solution in Query(self.predicate).solve(lookup):
            for predicate in self.conclusions.substitute([solution.context]):
                if fact := predicate.as_fact:
                    yield (fact, solution.derived_from)


def rule(
    attributes: AttrDict,
    predicate: PredicateTuples,
    *,
    implies: PredicateTuples,
) -> Rule:
    return Rule(
        Predicate.from_tuples(predicate, attributes),
        Predicate.from_tuples(implies, attributes),
    )


InferredFacts = t.Iterable[tuple[Fact[Ordinal], str, set[Fact[Ordinal]]]]


def run_rules_matching(
    facts: t.Iterable[Fact[Ordinal]],
    rules: t.Sequence[Rule],
    lookup: LookUpFunction[TOrdinal],
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
    lookup: LookUpFunction[TOrdinal],
) -> InferredFacts:
    return _run_rules(
        ((rule, rule.id) for rule in rules),
        lookup,
    )


def _run_rules(
    rules_and_original_ids: t.Iterable[tuple[Rule, str]],
    lookup: LookUpFunction[TOrdinal],
) -> InferredFacts:
    for rule, original_rule_id in rules_and_original_ids:
        for fact, bases in rule.run(lookup):
            yield fact, original_rule_id, bases
