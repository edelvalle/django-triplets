import typing as t
from dataclasses import dataclass, field, replace
from functools import cached_property
from hashlib import shake_128
from itertools import chain

Fact = tuple[str, str, str]


Context = dict[str, t.Any]


def storage_hash(text):
    """Returns a 32 chars string hash"""
    return shake_128(text.encode()).hexdigest(16)


@dataclass(slots=True)
class Solution:
    context: Context
    derived_from: frozenset[Fact]

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


@dataclass(slots=True)
class In:
    name: str
    values: set[str]


@dataclass(slots=True)
class Var:
    name: str


Expression = str | Var | In


def expression_matches(
    expression: Expression, value: str
) -> t.Optional[dict[str, str]]:
    """Returns the micro solution of matching an Expression over a value.

    Returning None means that there was no match
    """
    if isinstance(expression, str):
        return {} if expression == value else None
    elif isinstance(expression, In):
        return {expression.name: value} if value in expression.values else None
    elif isinstance(expression, Var):
        return {expression.name: value}
    else:
        return None


def substitute_using(
    expression: Var | In, contexts: list[Context]
) -> Expression:
    values = {
        value
        for ctx in contexts
        if (value := ctx.get(expression.name)) is not None
    }
    if not values:
        # no values found means that the variable still not defined
        return expression
    elif len(values) == 1:
        # just one value found means that this is now a literal
        return values.pop()
    else:
        # a few values found means this is an In expression
        return In(expression.name, values)


@dataclass(frozen=True)
class Clause(t.Iterable):
    subject: Expression
    verb: str
    obj: Expression

    def __iter__(self) -> t.Iterator[Expression]:
        return iter([self.subject, self.verb, self.obj])

    def substitute_using(self, contexts: list[Context]):
        """Replaces variables in this predicate with their values form the
        context
        """
        # This is an optimization
        if not contexts:
            return self

        clause = self
        for name, value in [("subject", self.subject), ("obj", self.obj)]:
            if isinstance(value, (Var, In)):
                new_value = substitute_using(value, contexts)
                clause = replace(clause, **{name: new_value})
        return clause

    def __lt__(self, other):
        """This is here for the sorting protocol and query optimization"""
        return self.sorting_key < other.sorting_key

    @cached_property
    def sorting_key(self):
        """The more defined (literal values) this clause has, the lower
        the sorting number will be. So it gets priority when performing queries.
        """
        weight = 0
        for value in [self.subject, self.obj]:
            if isinstance(value, In):
                weight += 1
            elif isinstance(value, Var):
                weight += 3
        return weight

    @property
    def variable_names(self) -> list[str]:
        return [
            expression.name
            for expression in [self.subject, self.obj]
            if isinstance(expression, (Var, In))
        ]

    @property
    def as_dict(self) -> dict[str, Expression]:
        return dict(self.__dict__)

    @property
    def as_triplet(self) -> t.Optional[tuple[str, str, str]]:
        if isinstance(self.subject, str) and isinstance(self.obj, str):
            return (self.subject, self.verb, self.obj)
        else:
            return None

    def matches(self, fact: Fact) -> t.Optional[Solution]:
        context: dict[str, str] = {}
        for expression, value in zip(self, fact):
            if (match := expression_matches(expression, value)) is None:
                return None
            else:
                context |= match
        return Solution(context, frozenset([fact]))


PredicateTuples = list[tuple[Expression, str, Expression]]


@dataclass(slots=True)
class Predicate(t.Iterable):
    clauses: list[Clause]

    @classmethod
    def from_tuples(
        cls: t.Type["Predicate"], predicate: PredicateTuples
    ) -> "Predicate":
        return cls([Clause(*clause) for clause in predicate])

    def optimized_by(self, contexts: list[Context]) -> list[Clause]:
        return list(sorted(self.substitute(contexts)))

    def substitute(self, contexts: list[Context]) -> t.Iterable[Clause]:
        return (clause.substitute_using(contexts) for clause in self)

    def matches(self, fact: Fact) -> t.Iterable[Solution]:
        return (
            solution
            for clause in self
            if (solution := clause.matches(fact)) is not None
        )

    @property
    def variable_names(self) -> set[str]:
        return set(chain(*[clause.variable_names for clause in self]))

    def __iter__(self) -> t.Iterator[Clause]:
        return iter(self.clauses)

    def __bool__(self) -> bool:
        return bool(self.clauses)

    def __add__(self, other) -> "Predicate":
        if isinstance(other, list):
            other = self.from_tuples(other)
        return replace(self, clauses=self.clauses + other.clauses)


LookUpFunction = t.Callable[[Clause], t.Iterable[Fact]]


@dataclass(slots=True)
class Query:
    predicate: Predicate
    solutions: list[Solution] = field(
        default_factory=lambda: [Solution({}, frozenset())]
    )

    @classmethod
    def from_tuples(
        cls: t.Type["Query"],
        predicate: PredicateTuples,
    ) -> "Query":
        return cls(Predicate.from_tuples(predicate))

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


@dataclass
class Rule:
    predicate: Predicate
    conclusions: Predicate

    @cached_property
    def id(self) -> str:
        """This is an 32 chars long string Unique ID to this rule predicate and
        conclusions, so it can be stored in a database and help to identify
        triplets generated by this rule.
        """
        return storage_hash(self.__repr__())

    def __post_init__(self):
        # validate
        missing_variables = (
            self.conclusions.variable_names - self.predicate.variable_names
        )
        if missing_variables:
            raise TypeError(
                f"{self} requires {missing_variables} in the predicate"
            )

    def matches(self, fact: Fact) -> t.Iterable["Rule"]:
        """If the `fact` matches this rule this function returns a rule
        that you can run `Rule.run` on to return the derived triplets
        """
        for match in self.predicate.matches(fact):
            predicate = self.predicate.substitute([match.context])
            conclusions = self.conclusions.substitute([match.context])
            yield replace(
                self,
                predicate=Predicate(list(predicate)),
                conclusions=Predicate(list(conclusions)),
            )

    def run(
        self,
        lookup: LookUpFunction,
    ) -> t.Iterable[tuple[tuple[str, str, str], frozenset[Fact]]]:
        for solution in Query(self.predicate).solve(lookup):
            for predicate in self.conclusions.substitute([solution.context]):
                if fact := predicate.as_triplet:
                    yield (fact, solution.derived_from)


def rule(
    predicate: PredicateTuples,
    *,
    implies: PredicateTuples,
) -> Rule:
    return Rule(
        Predicate.from_tuples(predicate), Predicate.from_tuples(implies)
    )


def run_rules_matching(
    facts: t.Iterable[Fact],
    rules: t.Sequence[Rule],
    lookup: LookUpFunction,
) -> t.Iterable[tuple[Fact, str, frozenset[Fact]]]:
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
) -> t.Iterable[tuple[Fact, str, frozenset[Fact]]]:
    return _run_rules(
        ((rule, rule.id) for rule in rules),
        lookup,
    )


def _run_rules(
    rules_and_original_ids: t.Iterable[tuple[Rule, str]],
    lookup: LookUpFunction,
) -> t.Iterable[tuple[Fact, str, frozenset[Fact]]]:
    for rule, original_rule_id in rules_and_original_ids:
        for fact, bases in rule.run(lookup):
            yield fact, original_rule_id, bases
