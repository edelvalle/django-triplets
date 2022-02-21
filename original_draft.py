from collections import defaultdict, namedtuple
from dataclasses import dataclass

_storage_key_mask: list[tuple[int, int, int]] = [
    (1, 1, 0),
    (0, 1, 1),
    (0, 1, 0),
]


@dataclass
class Var:
    name: str


class Triplet(namedtuple("Triplet", ["subject", "verb", "obj"])):
    def context_from(self, other):
        context = {}
        if isinstance(self.subject, Var):
            context[self.subject.name] = other.subject
        if isinstance(self.obj, Var):
            context[self.obj.name] = other.obj
        return context

    def hydrated_from(self, context):
        triplet = self
        if isinstance(self.subject, Var):
            triplet = Triplet(
                context.get(self.subject.name, "_"), triplet.verb, triplet.obj
            )
        if isinstance(self.obj, Var):
            triplet = Triplet(
                triplet.subject, triplet.verb, context.get(self.obj.name, "_")
            )
        return triplet

    def lookup_key_and_variable_names(self, context):
        triplet = self.hydrated_from(context)
        variable_names = [
            term.name
            for value, term in zip(triplet, self)
            if value == "_" and isinstance(term, Var)
        ]
        return ":".join(triplet), variable_names

    @property
    def storage_keys_and_values(self):
        for mask in _storage_key_mask:
            keys = [
                (term if in_key else "_") for (term, in_key) in zip(self, mask)
            ]
            value = tuple(
                term for (term, in_key) in zip(self, mask) if not in_key
            )
            yield ":".join(keys), value

    def matches(self, other):
        match self:
            case (Var(_), str(verb), Var(_)):
                matches = verb == other.verb
            case (str(subject), str(verb), Var(_)):
                matches = subject == other.subject and verb == other.verb
            case (Var(_), str(verb), str(obj)):
                matches = verb == other.verb and obj == other.obj
            case _:
                matches = self == other
        return matches


class Rule:
    query = []
    implies = []

    @classmethod
    def is_a_trigger_queries_and_context(cls, triplet) -> bool:
        context = {}
        query = []
        for predicate in cls.query:
            if (
                not context
                and isinstance(predicate, Triplet)
                and predicate.matches(triplet)
            ):
                context.update(predicate.context_from(triplet))
            else:
                query.append(predicate)
        return len(query) != len(cls.query), query, context

    @classmethod
    def implied_triplets(cls, solutions):
        for solution in solutions:
            for implication in cls.implies:
                yield implication.hydrated_from(solution)


class Database:
    def __init__(self, rules: list[Rule]) -> None:
        self._svo = defaultdict(set)
        self._rules = rules

    def add(self, subject, verb, obj):
        self._add(Triplet(subject, verb, obj))

    def _add(self, triplet):
        for key, value in triplet.storage_keys_and_values:
            self._svo[key].add(value)
        for rule in self._rules:
            (
                is_trigger,
                query,
                context,
            ) = rule.is_a_trigger_queries_and_context(triplet)
            if is_trigger:
                print("> ", triplet, query, context)
                for implication in rule.implied_triplets(
                    self.query(query, context)
                ):
                    print("implies>", implication)
                    self._add(implication)

    def remove(self, subject, verb, obj):
        triplet = Triplet(subject, verb, obj)
        for key, value in triplet.storage_keys_and_values:
            self._svo[key].remove(value)

    def query(self, queries: list[Triplet], context=None):
        context = context or {}
        match queries:
            case []:
                yield context
            case [predicate, *query]:
                if callable(predicate):
                    if predicate(**context):
                        yield context
                else:
                    key, variables = predicate.lookup_key_and_variable_names(
                        context
                    )
                    for values in self._svo[key]:
                        local_context = context | {
                            variable: value
                            for variable, value in zip(variables, values)
                        }
                        yield from self.query(query, local_context)


class SiblingsRule(Rule):
    query = [
        Triplet(Var("child1"), "child_of", Var("parent")),
        Triplet(Var("child2"), "child_of", Var("parent")),
        lambda child1, child2, **kw: child1 != child2,
    ]

    implies = [Triplet(Var("child1"), "sibling_of", Var("child2"))]


d = Database(rules=[SiblingsRule])
d.add("ll", "child_of", "a")
d.add("a", "child_of", "b")
d.add("b", "child_of", "c")
d.add("x", "child_of", "c")

for result in d.query([Triplet("a", "child_of", Var("parent"))]):
    print(result)
# > {'parent': 'b'}

for result in d.query(
    [
        Triplet(Var("grandson"), "child_of", Var("parent")),
        Triplet(Var("parent"), "child_of", Var("grandfather")),
    ]
):
    print(result)
# > {'grandson': 'a', 'parent': 'b', 'grandfather': 'c'}
# > {'grandson': 'll', 'parent': 'a', 'grandfather': 'b'}

for result in d.query(
    [
        Triplet(Var("brother1"), "sibling_of", Var("brother2")),
    ]
):
    print(result)
