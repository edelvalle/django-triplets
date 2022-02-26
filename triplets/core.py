import typing as t
from dataclasses import dataclass, field, replace
from functools import cached_property
from hashlib import shake_128
from itertools import chain

Triplet = tuple[str, str, str]


Context = dict[str, t.Any]


def storage_hash(text):
    """Returns a 32 chars string hash"""
    return shake_128(text.encode()).hexdigest(16)


@dataclass(frozen=True, slots=True)
class Solution:
    context: Context
    derived_from: frozenset[Triplet]

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


@dataclass(frozen=True, slots=True)
class In:
    name: str
    values: set[str]


@dataclass(frozen=True, slots=True)
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
class Predicate(t.Iterable):
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

        predicate = self
        for name, value in [("subject", self.subject), ("obj", self.obj)]:
            if isinstance(value, (Var, In)):
                new_value = substitute_using(value, contexts)
                predicate = replace(predicate, **{name: new_value})
        return predicate

    def __lt__(self, other):
        """This is here for the sorting protocol and query optimization"""
        return self.sorting_key < other.sorting_key

    @cached_property
    def sorting_key(self):
        """The more defined (literal values) this predicate has, the lower
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

    def matches(self, triplet: Triplet) -> t.Optional[Solution]:
        context: dict[str, str] = {}
        for expression, value in zip(self, triplet):
            if (match := expression_matches(expression, value)) is None:
                return None
            else:
                context |= match
        return Solution(context, frozenset([triplet]))


ListOfPredicateTuples = list[tuple[Expression, str, Expression]]


@dataclass(frozen=True, slots=True)
class Predicates(t.Iterable):
    items: list[Predicate]

    @classmethod
    def from_tuples(
        cls: t.Type["Predicates"], predicates: ListOfPredicateTuples
    ) -> "Predicates":
        return cls([Predicate(*predicate) for predicate in predicates])

    def optimized_by(self, contexts: list[Context]) -> list[Predicate]:
        return list(sorted(self.substitute(contexts)))

    def substitute(self, contexts: list[Context]) -> t.Iterable[Predicate]:
        return (predicate.substitute_using(contexts) for predicate in self)

    def matches(self, triplet: Triplet) -> t.Iterable[Solution]:
        return (
            solution
            for predicate in self
            if (solution := predicate.matches(triplet)) is not None
        )

    @property
    def variable_names(self) -> set[str]:
        return set(chain(*[predicate.variable_names for predicate in self]))

    def __iter__(self) -> t.Iterator[Predicate]:
        return iter(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)

    def __add__(self, other) -> "Predicates":
        if isinstance(other, list):
            other = self.from_tuples(other)
        return replace(self, items=self.items + other.items)


LookUpFunction = t.Callable[[Predicate], t.Iterable[Triplet]]


@dataclass(slots=True)
class Query:
    predicates: Predicates
    solutions: list[Solution] = field(
        default_factory=lambda: [Solution({}, frozenset())]
    )

    @classmethod
    def from_tuples(
        cls: t.Type["Query"],
        predicates: ListOfPredicateTuples,
    ) -> "Query":
        return cls(Predicates.from_tuples(predicates))

    @property
    def optimized_predicates(self) -> list[Predicate]:
        return self.predicates.optimized_by([s.context for s in self.solutions])

    def solve(self, lookup: LookUpFunction) -> t.List[Solution]:
        if self.predicates and self.solutions:
            predicate, *predicates = self.optimized_predicates
            predicate_solutions = [
                match
                for triplet in lookup(predicate)
                if (match := predicate.matches(triplet)) is not None
            ]
            next_query = Query(
                Predicates(predicates),
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
    predicates: Predicates
    conclusions: Predicates

    @cached_property
    def id(self) -> str:
        """This is an 32 chars long string Unique ID to this rule predicates and
        conclusions, so it can be stored in a database and help to identify
        triplets generated by this rule.
        """
        return storage_hash(self.__repr__())

    def __post_init__(self):
        # validate
        missing_variables = (
            self.conclusions.variable_names - self.predicates.variable_names
        )
        if missing_variables:
            raise TypeError(
                f"{self} requires {missing_variables} in its predicates"
            )

    def matches(self, triplet: Triplet) -> t.Iterable["Rule"]:
        """If the `triplet` matches this rule this function returns a rule
        that you can run `Rule.run` on to return the derived triplets
        """
        for match in self.predicates.matches(triplet):
            predicates = self.predicates.substitute([match.context])
            conclusions = self.conclusions.substitute([match.context])
            yield replace(
                self,
                predicates=Predicates(list(predicates)),
                conclusions=Predicates(list(conclusions)),
            )

    def run(
        self,
        lookup: LookUpFunction,
    ) -> t.Iterable[tuple[tuple[str, str, str], frozenset[Triplet]]]:
        for solution in Query(self.predicates).solve(lookup):
            for predicate in self.conclusions.substitute([solution.context]):
                if triplet := predicate.as_triplet:
                    yield (triplet, solution.derived_from)


def rule(
    predicates: ListOfPredicateTuples,
    *,
    implies: ListOfPredicateTuples,
) -> Rule:
    return Rule(
        Predicates.from_tuples(predicates), Predicates.from_tuples(implies)
    )


# AddOrRemoveFunction = t.Callable[[Triplet, str, frozenset[Triplet]], t.Any]
AddOrRemoveFunction = t.Callable[
    [str, t.Iterable[tuple[Triplet, frozenset[Triplet]]]],
    t.Any,
]


def run_rules_matching(
    triplet: Triplet,
    rules: t.Iterable[Rule],
    lookup: LookUpFunction,
    add: AddOrRemoveFunction,
):
    matching_rules = (
        (matching_rule, rule.id)
        for rule in rules
        for matching_rule in rule.matches(triplet)
    )
    _run_rules(matching_rules, lookup, add)


def refresh_rules(
    rules: t.Iterable[Rule], lookup: LookUpFunction, add: AddOrRemoveFunction
):
    _run_rules(((rule, rule.id) for rule in rules), lookup, add)


def _run_rules(
    rules_and_ids: t.Iterable[tuple[Rule, str]],
    lookup: LookUpFunction,
    add: AddOrRemoveFunction,
):
    for rule, original_rule_id in rules_and_ids:
        add(original_rule_id, rule.run(lookup))
