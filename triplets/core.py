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
        clause_before_substitution: "Clause",
    ) -> t.Iterable["Solution"]:
        for solution in solutions:
            # two solutions can merge when:
            # - we don't share the same facts in `derived_from`
            # - we can merge our contexts without override
            #   (meaning that their union is commutative)
            # - and the fact from which is derived a new solution
            #   satisfies the clause_before_substitution constrain
            if (
                (
                    not self.derived_from
                    or not self.derived_from.issubset(solution.derived_from)
                )
                and (context := (self.context | solution.context))
                == (solution.context | self.context)
                and self.satisfies_constrain(
                    clause_before_substitution, solution
                )
            ):
                yield Solution(
                    context=context,
                    derived_from=self.derived_from | solution.derived_from,
                )

    def satisfies_constrain(
        self, clause_before_substitution: "Clause", solution: "Solution"
    ) -> bool:
        fact = next(iter(solution.derived_from))
        constrain = clause_before_substitution.substitute([self.context])
        return bool(list(constrain.matches(fact)))


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

    @property
    def can_be_solved(self) -> bool:
        left = set(
            t.cast(
                VarTypes.T,
                LookUpExpression.variable_types(self.entity).value,
            )
        )
        right = set(
            t.cast(
                VarTypes.T,
                LookUpExpression.variable_types(self.value).value,
            )
        )
        return len(left) <= 1 and len(right) <= 1

    def substitute(self, contexts: list[Context]):
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
    clauses_before_substitution: dict[Clause, Clause]
    variables_types: VarTypes.T
    was_planned: bool

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
        self,
        clauses: list[Clause],
        variables_types: VarTypes.T | None = None,
        clauses_before_substitution: dict[Clause, Clause] | None = None,
        was_planned: bool = False,
    ):
        self.clauses = clauses
        self.clauses_before_substitution = clauses_before_substitution or {}
        self.was_planned = was_planned
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
        if self.was_planned:
            return self

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
            selected_clause = first(priorized_clauses)
            if selected_clause is not None:
                result.append(selected_clause)
                solved_variables.update(
                    solvable_clauses_to_vars[selected_clause]
                )
                unsolved_clauses = {
                    clause: (left - solved_variables, right - solved_variables)
                    for clause, (left, right) in unsolved_clauses.items()
                    if clause != selected_clause
                }

        return replace(self, clauses=result, was_planned=True)

    def substitute(self, contexts: list[Context]) -> "Predicate":
        # Is very important here to preserve the order of the clauses,
        # because if this predicate was already "query planned" that order
        # matters.
        # We also need to keep a map to the clauses before substitution happens

        # This trick relies in the fact that dicts in python perserve insertion
        # order
        clauses = {clause.substitute(contexts): clause for clause in self}
        return replace(
            self,
            clauses=list(clauses),
            clauses_before_substitution=clauses,
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
        return cls(Predicate.from_tuples(attributes, predicate))

    def solve(self, lookup: LookUpFunction) -> t.List[Solution]:
        if self.predicate and self.solutions:
            predicate = self.predicate.substitute(
                [s.context for s in self.solutions]
            ).planned

            clause, *clauses = predicate

            # local solutions
            solutions = list(
                chain(*(clause.matches(fact) for fact in lookup(clause)))
            )

            clauses_before_substitution = predicate.clauses_before_substitution[
                clause
            ]

            # local solutions merged with my solution
            solutions = list(
                chain(
                    *[
                        solution.merge(solutions, clauses_before_substitution)
                        for solution in self.solutions
                    ]
                )
            )

            predicate = replace(predicate, clauses=clauses)
            return Query(predicate, solutions).solve(lookup)
        else:
            return self.solutions


@dataclass(init=False)
class Rule:
    name: str
    predicate: Predicate
    implies: Predicate
    _solution: Solution
    _variable_types: VarTypes.T

    def __init__(
        self,
        name: str,
        predicate: Predicate,
        implies: Predicate,
        _solution: Solution | None = None,
        _variable_types: VarTypes.T | None = None,
    ):
        self.name = name
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
        return f"{self.name}: {self.predicate} => {self.implies}"

    def matches(self, fact: Fact) -> t.Iterable["Rule"]:
        """If the `fact` matches this rule this function returns a rule
        that you can run `Rule.run` on to return the derived facts
        """
        for clause, match in self.predicate.matches(fact):
            # this new predicate does not include the clause that matched
            # and has a substitution done by the found results

            # remove the matched clause from the predicate
            predicate = replace(
                self.predicate,
                clauses=[c for c in self.predicate if c != clause],
            )

            # but if the current clause has too many variables and can't be
            # solved, then we substitute the current solution and reinsert it
            # in the predicate
            if not clause.can_be_solved:
                predicate.clauses.append(clause.substitute([match.context]))

            yield replace(
                self,
                predicate=predicate,
                _solution=match,
            )

    def run(
        self,
        lookup: LookUpFunction,
    ) -> t.Iterable[tuple[Fact, set[Fact]]]:
        for solution in Query(self.predicate, [self._solution]).solve(lookup):
            for fact in self.implies.evaluate(solution.context):
                yield (fact, solution.derived_from)


class RuleProtocol(t.Protocol):
    __name__: str
    predicate: PredicateTuples
    implies: PredicateTuples


def compile_rules(attributes: AttrDict, *rules: RuleProtocol) -> list[Rule]:
    return [
        Rule(
            r.__name__,
            Predicate.from_tuples(attributes, r.predicate).planned,
            Predicate.from_tuples(attributes, r.implies).planned,
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


T = t.TypeVar("T")


def first(iterable: t.Iterable[T]) -> T | None:
    return next(iter(iterable), None)
