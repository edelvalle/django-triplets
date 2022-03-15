import typing as t
from dataclasses import dataclass, field, replace
from functools import cached_property
from hashlib import shake_128
from itertools import chain
from types import TracebackType

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

    @classmethod
    def new_empty(cls) -> "Solution":
        return cls({}, set())

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
        if attr not in attributes:
            raise TypeError(f"Unknown attribute: {attr}")
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

    def matches(self, fact: Fact) -> t.Iterable[Solution]:
        entity, attr, value = fact
        if self.attr == attr:
            # Why do entity first and cache it?
            # because it's the simplest expression for sure
            entity_matches = list(LookUpExpression.matches(self.entity, entity))
            for value_match in LookUpExpression.matches(self.value, value):
                for entity_match in entity_matches:
                    yield Solution(entity_match | value_match, {fact})


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

    @property
    def planned(self) -> "Predicate":
        """Assumes tha this predicate is a query and orders the clauses to
        perform an optimal query
        """
        result: list[Clause] = []
        solved_variables: set[str] = set()
        # by this time the variables types are Ok
        unsolved_clauses = {
            clause: (
                set(
                    t.cast(
                        VarTypes.T,
                        LookUpExpression.variable_types(clause.entity).value,
                    )
                ),
                set(
                    t.cast(
                        VarTypes.T,
                        LookUpExpression.variable_types(clause.value).value,
                    )
                ),
            )
            for clause in self
        }
        while unsolved_clauses:
            # this are clauses with max 1 var per side
            solvable_clauses_to_vars = {
                clause: left.union(right)
                for clause, (left, right) in unsolved_clauses.items()
                if len(left) <= 1 and len(right) <= 1
            }
            if not solvable_clauses_to_vars:
                raise RuntimeError(
                    f"Can't solve {self}, unsolved clauses: {unsolved_clauses}"
                )

            # the less variables the clause has the better
            # if it has a variable of type Any, as it will probably produce many
            # results, that one will go to the end of the tail to have it very
            # constrained during lookup
            priorized_clauses = sorted(
                solvable_clauses_to_vars,
                key=lambda clause: sum(
                    # Make the `Any` matcher very expensive
                    (10 if var_name.startswith("*") else 1)
                    for var_name in solvable_clauses_to_vars[clause]
                ),
            )

            # We pick the first one and continue
            for selected_clause in priorized_clauses:
                result.append(selected_clause)
                solved_variables.update(
                    solvable_clauses_to_vars[selected_clause]
                )
                unsolved_clauses = {
                    clause: (left - solved_variables, right - solved_variables)
                    for clause, (left, right) in unsolved_clauses.items()
                    if clause != selected_clause
                }
                break
        return replace(self, clauses=result)

    def substitute(self, contexts: list[Context]) -> "Predicate":
        return replace(
            self, clauses=[clause.substitute_using(contexts) for clause in self]
        )

    def evaluate(self, context: Context) -> t.Iterable[Fact]:
        for clause in self.substitute([context]):
            if (fact := clause.as_fact) is not None:
                yield fact

    def matches(self, fact: Fact) -> t.Iterable[tuple[Clause, Solution]]:
        for clause in self:
            for match in clause.matches(fact):
                yield clause, match

    def __iter__(self) -> t.Iterator[Clause]:
        return iter(self.clauses)

    def __bool__(self) -> bool:
        return bool(self.clauses)


LookUpFunction = t.Callable[[Clause], t.Iterable[Fact]]


@dataclass(slots=True)
class Query:
    predicate: Predicate
    solutions: list[Solution] = field(
        default_factory=lambda: [Solution.new_empty()]
    )

    @classmethod
    def from_tuples(
        cls: type["Query"],
        attributes: AttrDict,
        predicate: PredicateTuples,
    ) -> "Query":
        return cls(Predicate.from_tuples(attributes, predicate).planned)

    def solve(self, lookup: LookUpFunction) -> t.List[Solution]:
        if self.predicate and self.solutions:
            clause, *predicate = self.predicate
            predicate_solutions = list(
                chain(*(clause.matches(fact) for fact in lookup(clause)))
            )

            next_query = Query(
                Predicate(predicate, self.predicate.variables_types),
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


@dataclass(init=False)
class Rule:
    predicate: Predicate
    implies: Predicate
    _solution: Solution
    _variable_types: VarTypes.T

    def __init__(
        self,
        predicate: Predicate,
        implies: Predicate,
        _solution: Solution | None = None,
        _variable_types: VarTypes.T | None = None,
    ):
        self.predicate = predicate
        self.implies = implies
        self._solution = _solution or Solution.new_empty()
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
        for clause, match in self.predicate.matches(fact):
            # this new predicate does not include the clause that matched
            # and has a substitution done by the found results
            predicate = Predicate(
                [c for c in self.predicate if c != clause],
                variables_types=self.predicate.variables_types,
            ).substitute([match.context])

            for solution in self._solution.merge([match]):
                yield replace(
                    self,
                    predicate=predicate,
                    implies=self.implies,
                    _variable_types=self._variable_types,
                    _solution=solution,
                )

    def run(
        self,
        lookup: LookUpFunction,
    ) -> t.Iterable[tuple[Fact, set[Fact]]]:
        for solution in Query(self.predicate).solve(lookup):
            for merged_solution in self._solution.merge([solution]):
                for fact in self.implies.evaluate(merged_solution.context):
                    yield (fact, merged_solution.derived_from)


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
