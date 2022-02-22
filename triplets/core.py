import typing as t
from dataclasses import dataclass, field, replace
from functools import cached_property
from itertools import chain

Context = dict[str, t.Any]


@dataclass(frozen=True, slots=True)
class In:
    name: str
    values: set[str]


@dataclass(frozen=True, slots=True)
class Var:
    name: str


Expression = str | Var | In


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
class Predicate:
    subject: Expression
    verb: str
    obj: Expression

    def substitute_using(self, contexts: list[Context]):
        """Replaces variables in this predicate with their values form the
        context
        """
        predicate = self
        for name, value in [("subject", self.subject), ("obj", self.obj)]:
            if isinstance(value, (Var, In)):
                new_value = substitute_using(value, contexts)
                predicate = replace(predicate, **{name: new_value})
        return predicate

    def __lt__(self, other: "Predicate"):
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

    @cached_property
    def variable_names(self) -> tuple[t.Optional[str], t.Optional[str]]:
        return (
            isinstance(self.subject, (Var, In)) and self.subject.name or None,
            isinstance(self.obj, (Var, In)) and self.obj.name or None,
        )

    def as_dict(self):
        return self.__dict__


class Triplet(t.Protocol):
    subject: str
    verb: str
    obj: str

    def __hash__(self) -> int:
        return hash((self.subject, self.verb, self.obj))


@dataclass(frozen=True, slots=True)
class Solution:
    context: Context
    derived_from: frozenset[Triplet]

    @property
    def context_set(self):
        return frozenset(self.context.items())

    def merge(self, solutions):
        for solution in solutions:
            # two solutions can merge when:
            # - we don't share the same facts
            # - we do share key-value in our context
            # - our contexts don't override their values when united
            #   (meaning that their union is commutative)
            if (
                not self.context
                and not self.derived_from
                or (
                    solution.derived_from.isdisjoint(self.derived_from)
                    and not solution.context_set.isdisjoint(self.context_set)
                    and (self.context | solution.context)
                    == (solution.context | self.context)
                )
            ):
                yield Solution(
                    context=self.context | solution.context,
                    derived_from=self.derived_from | solution.derived_from,
                )


class Database(t.Protocol):
    def lookup(self, predicate: Predicate) -> t.Iterable[Triplet]:
        pass


@dataclass(frozen=True, slots=True)
class Query:
    predicates: list[Predicate]
    solutions: list[Solution] = field(
        default_factory=lambda: [Solution({}, frozenset())]
    )

    def solve_using(self, database: Database) -> t.Iterable[Solution]:
        optimized_predicates = self._optimized_predicates
        if isinstance(optimized_predicates, list):
            if optimized_predicates:
                predicate, *predicates = optimized_predicates
                predicate_solutions = [
                    Solution(
                        {
                            variable: value
                            for variable, value in zip(
                                predicate.variable_names,
                                [triplet.subject, triplet.obj],
                            )
                            if variable
                        },
                        frozenset([triplet]),
                    )
                    for triplet in database.lookup(predicate)
                ]

                next_query = type(self)(
                    predicates,
                    solutions=list(
                        chain(
                            *[
                                solution.merge(predicate_solutions)
                                for solution in self.solutions
                            ]
                        )
                    ),
                )
                return next_query.solve_using(database)
            else:
                return self.solutions
        else:
            return []

    @property
    def _optimized_predicates(self):
        contexts = [s.context for s in self.solutions]
        return list(
            sorted(
                predicate.substitute_using(contexts)
                for predicate in self.predicates
            )
        )
