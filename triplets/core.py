import inspect
import typing as t
from collections import defaultdict
from dataclasses import dataclass, field, replace
from functools import cached_property
from hashlib import shake_128
from itertools import chain

from .ast import (
    AttrDict,
    Context,
    EntityExpression,
    Fact,
    Ordinal,
    OrdinalTypes,
    TypedAny,
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


ClauseTuple = tuple[EntityExpression, str, ValueExpression]
PredicateTuples = t.Sequence[ClauseTuple]


@dataclass(frozen=True)
class Clause:
    subject: TypedExpression
    verb: str
    obj: TypedExpression

    @classmethod
    def from_tuple(
        cls: type["Clause"],
        clause: ClauseTuple,
        attributes: AttrDict,
    ) -> "Clause":
        entity, attr, value = clause
        return cls(
            typed_from_entity(entity),
            attr,
            typed_from_value(value, attributes[attr]),
        )

    def __repr__(self) -> str:
        return f"({self.subject}, {self.verb}, {self.obj})"

    def substitute_using(self, contexts: list[Context]):
        """Replaces variables in this predicate with their values form the
        context
        """
        # This is an optimization
        if not contexts:
            return self

        new_subject = substitute_using(self.subject, contexts)
        new_obj = substitute_using(self.obj, contexts)
        return replace(self, subject=new_subject, obj=new_obj)

    def __lt__(self, other: "Clause") -> bool:
        """This is here for the sorting protocol and query optimization"""
        return self.sorting_key < other.sorting_key

    @cached_property
    def sorting_key(self) -> int:
        """The more defined (literal values) this clause has, the lower
        the sorting number will be. So it gets priority when performing queries.
        """
        return expression_weight(self.subject) + expression_weight(self.obj)

    @property
    def variable_types(self) -> defaultdict[str, set[type[Ordinal]]]:
        variable_types: defaultdict[str, set[type[Ordinal]]] = defaultdict(set)
        if name := expression_var_name(self.subject):
            variable_types[name].add(expression_type(self.subject))
        if name := expression_var_name(self.obj):
            variable_types[name].add(expression_type(self.obj))
        return variable_types

    @property
    def as_fact(self) -> t.Optional[Fact]:
        if isinstance(self.subject, str) and isinstance(self.obj, Ordinal):
            return (self.subject, self.verb, self.obj)
        else:
            return None

    def matches(self, fact: Fact) -> t.Optional[Solution]:
        subject, verb, obj = fact
        if self.verb != verb:
            return None
        if (subject_match := expression_matches(self.subject, subject)) is None:
            return None
        if (obj_match := expression_matches(self.obj, obj)) is None:
            return None
        return Solution(subject_match | obj_match, {fact})


VariableTypes = dict[str, type[Ordinal]]


@dataclass(slots=True)
class Predicate(t.Iterable[Clause]):
    clauses: list[Clause]

    @classmethod
    def from_tuples(
        cls: type["Predicate"],
        attributes: AttrDict,
        predicate: PredicateTuples,
    ) -> "Predicate":
        return cls(
            [Clause.from_tuple(clause, attributes) for clause in predicate]
        )

    def __post_init__(self):
        # validate that the types of all variables are coherent
        # this will raise if
        self.variable_types

    def __repr__(self) -> str:
        return str(self.clauses)

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
    def variable_types(self) -> VariableTypes:
        variable_types: defaultdict[str, set[type[Ordinal]]] = defaultdict(set)
        for clause in self.clauses:
            for name, types in clause.variable_types.items():
                variable_types[name].update(types)

        result: VariableTypes = {}
        for var_name, types in variable_types.items():
            if len(types) == 1:
                result[var_name] = types.pop()
            else:
                raise TypeError(
                    f"Variable `{var_name}` can't have more than one type, and "
                    f"it has: {[t.__name__ for t in types]}"
                )
        return result

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


@dataclass(slots=True)
class Conclusions:
    Function = t.Callable[..., t.Iterable[Fact]]

    conclusions: Predicate | Function

    @classmethod
    def from_tuples(
        cls: type["Conclusions"],
        attributes: AttrDict,
        predicate: PredicateTuples | Function,
    ) -> "Conclusions":
        if callable(predicate):
            return cls(predicate)
        else:
            return cls(Predicate.from_tuples(attributes, predicate))

    def __repr__(self) -> str:
        if callable(self.conclusions):
            return f"f{inspect.signature(self.conclusions)}"
        else:
            return str(self.conclusions)

    @property
    def has_any_type(self) -> bool:
        if isinstance(self.conclusions, Predicate):
            return any(
                isinstance(c.subject, TypedAny) or isinstance(c.obj, TypedAny)
                for c in self.conclusions.clauses
            )
        else:
            return False

    def evaluate(self, context: Context) -> t.Iterable[Fact]:
        if isinstance(self.conclusions, Predicate):
            for clause in self.conclusions.substitute([context]):
                if (fact := clause.as_fact) is not None:
                    yield fact
        else:
            yield from self.conclusions(**context)

    @property
    def variable_types(
        self,
    ) -> t.Iterable[tuple[str, t.Optional[type[Ordinal]]]]:
        if isinstance(self.conclusions, Predicate):
            yield from self.conclusions.variable_types.items()
        else:
            params = inspect.signature(self.conclusions).parameters.values()
            for param in params:
                if param.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    param_type = (
                        param.annotation
                        if param.annotation in OrdinalTypes
                        else None
                    )
                    yield param.name, param_type


@dataclass
class Rule:
    predicate: Predicate
    conclusions: Conclusions
    _context: Context = field(default_factory=dict)

    @cached_property
    def id(self) -> str:
        """This is an 32 chars long string Unique ID to this rule predicate and
        conclusions, so it can be stored in a database and help to identify
        facts generated by this rule.
        """
        return storage_hash(self.__repr__())

    def validate(self) -> "Rule":
        predicate_vars = self.predicate.variable_types
        err_msgs: list[str] = []
        for var_name, var_type in self.conclusions.variable_types:
            if (predicate_var_type := predicate_vars.get(var_name)) is not None:
                if var_type is not None and not issubclass(
                    var_type, predicate_var_type
                ):
                    err_msgs.append(
                        f"Type mismatch in variable `?{var_name}`, "
                        f"got {predicate_var_type}, requires: {var_type}",
                    )
            else:
                err_msgs.append(
                    f"Variable `?{var_name}: {var_type}` is missing in the predicate"
                )

        if self.conclusions.has_any_type:
            err_msgs.append(f"Implications can't have `?` in them")

        if err_msgs:
            raise TypeError("\n - ".join([f"Error(s) in {self}:"] + err_msgs))
        return self

    def __repr__(self) -> str:
        return f"Rule: {self.predicate} => {self.conclusions}"

    def matches(self, fact: Fact) -> t.Iterable["Rule"]:
        """If the `fact` matches this rule this function returns a rule
        that you can run `Rule.run` on to return the derived facts
        """
        for match in self.predicate.matches(fact):
            predicate = self.predicate.substitute([match.context])
            yield replace(
                self,
                predicate=Predicate(list(predicate)),
                conclusions=self.conclusions,
                _context=self._context | match.context,
            )

    def run(
        self,
        lookup: LookUpFunction,
    ) -> t.Iterable[tuple[Fact, set[Fact]]]:
        for solution in Query(self.predicate).solve(lookup):
            for fact in self.conclusions.evaluate(
                self._context | solution.context
            ):
                yield (fact, solution.derived_from)


class RuleProtocol(t.Protocol):
    predicate: PredicateTuples
    implies: PredicateTuples | Conclusions.Function


def compile_rules(attributes: AttrDict, *rules: RuleProtocol) -> list[Rule]:
    return [
        Rule(
            Predicate.from_tuples(attributes, r.predicate),
            Conclusions.from_tuples(attributes, r.implies),
        ).validate()
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
