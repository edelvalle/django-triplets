import typing as t
from dataclasses import dataclass, field, replace
from functools import cached_property

Context = dict[str, t.Any]
Solution = dict[str, t.Any]


@dataclass
class Var:
    name: str

    def substitute_using(self, context: Context):
        return context.get(self.name, self)


Expression = str | Var


@dataclass
class Predicate:
    subject: Expression
    verb: str
    obj: Expression

    def substitute_using(self, context: Context):
        """Replaces variables in this predicate with their values form the
        context
        """
        predicate = self
        if isinstance(self.subject, Var):
            predicate = replace(
                predicate, subject=self.subject.substitute_using(context)
            )
        if isinstance(self.obj, Var):
            predicate = replace(
                predicate, obj=self.obj.substitute_using(context)
            )
        return predicate

    def __lt__(self, other: "Predicate"):
        """This is here for the sorting protocol and query optimization"""
        return self.sorting_key < other.sorting_key

    @cached_property
    def sorting_key(self):
        """The more defined (literal values) this predicate has, the lower
        the sorting number will be. So it gets priority when performing queries.
        """
        return isinstance(self.subject, Var) + isinstance(self.obj, Var)

    @cached_property
    def variable_names(self) -> tuple[t.Optional[str], t.Optional[str]]:
        return (
            isinstance(self.subject, Var) and self.subject.name or None,
            isinstance(self.obj, Var) and self.obj.name or None,
        )

    def as_dict(self):
        return self.__dict__


class Triplet(t.Protocol):
    subject: str
    verb: str
    obj: str


class Database(t.Protocol):
    def lookup(
        self,
        predicate: Predicate,
        consumed: list[Triplet],
    ) -> t.Iterable[Triplet]:
        pass


@dataclass
class Query:
    predicates: list[Predicate]
    context: Context = field(default_factory=dict)
    consumed: list[Triplet] = field(default_factory=list)

    def solve_using(self, database: Database) -> t.Iterable[Solution]:
        if optimized_predicates := self._optimized_predicates:
            predicate, *predicates = optimized_predicates
            for solution in database.lookup(predicate, self.consumed):
                local_context = self.context | {
                    variable: value
                    for variable, value in zip(
                        predicate.variable_names,
                        [solution.subject, solution.obj],
                    )
                    if variable
                }
                subquery = type(self)(
                    predicates,
                    local_context,
                    self.consumed + [solution],
                )
                yield from subquery.solve_using(database)
        else:
            yield self.context

    @property
    def _optimized_predicates(self):
        return list(
            sorted(p.substitute_using(self.context) for p in self.predicates)
        )
