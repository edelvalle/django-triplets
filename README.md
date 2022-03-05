[![Run tests](https://github.com/edelvalle/django-triplets/actions/workflows/github-actions-test.yml/badge.svg)](https://github.com/edelvalle/django-triplets/actions/workflows/github-actions-test.yml)

# Django Triplets

**No yet in pypi and NOT PRODUCTION READY for sure**

Bring some declarative logic programming into Django

## Installation

```bash
pip install django-triplets
```

Register the app in your INSTALLED_APPS

```python
INSTALLED_APPS = [
    ...
    "triplets",
    ...
]
```

The configuration options are:

```python
# use the helper `triplets.rule` to create rules
TRIPLETS_INFERENCE_RULES: list[fact.Rule] = []
```

## Usage

Do you remember Prolog? or Datalog? Well, this is kind of that.

Given a Knowledge Base where each Fact is represented as a Triplate in the form
`Fact(subject, verb, object)`, you can represent things like:

```python
facts = [
    # germany facts
    ("mitte", "located_in", "berlin"),
    ("spandau", "located_in", "berlin"),
    ("berlin", "located_in", "germany"),
    ("germany", "located_in", "europe"),

    # france facts
    ("paris", "located_in", "france"),
    ("france", "located_in", "europe"),

    # spain facts
    ("madrid", "located_in", "spain"),
    ("valencia", "located_in", "spain"),
    ("spain", "located_in", "europe"),

    # world facts
    ("europe", "located_in", "world"),
]
```

This set of `facts` represents a directed graph where the verbs are the edges
and subjects/objects the nodes?.

You can store this in the database by doing:

```python
from triplets import api

api.bulk_add(facts)
```

After that you can make queries like:

```python
answers = api.solve([(Var("country"), "located_in", "europe")])
assert answers == [
    {"country": "germany"},
    {"country": "france"},
    {"country": "spain"},
]
```

Notice that `Var(name)` describes a placeholder and when a solution for that
particular query is found, the name of the variable will be in the answers.

Let's see another example, you can do the following if you wanna query all
cities inside of European countries:

```python
answers = api.solve([
    (Var("city"), "located_in", Var("country")),
    (Var("country"), "located_in", "europe"),
])

assert answers == [
    {'country': 'germany', 'city': 'berlin'},
    {'country': 'france', 'city': 'paris'},
    {'country': 'spain', 'city': 'madrid'},
    {'country': 'spain', 'city': 'valencia'},
]
```

If you want to understand where all that is coming from, how did the solver
arrived to that conclusion use `triplets.api.explain_solutions()` and you will
see each Solution from which facts is derived from:

```python
answers = api.explain_solutions([
    (Var("city"), "located_in", Var("country")),
    (Var("country"), "located_in", "europe"),
])

assert answers == [
    Solution(
        {'country': 'germany', 'city': 'berlin'},
        derived_from=frozenset({
            ('berlin', 'located_in', 'germany'),
            ('germany', 'located_in', 'europe')
        })
    ),
    Solution(
        {'country': 'france', 'city': 'paris'},
        derived_from=frozenset({
            ('france', 'located_in', 'europe'),
            ('paris', 'located_in', 'france')
        })
    ),
    Solution(
        {'country': 'spain', 'city': 'madrid'},
        derived_from=frozenset({
            ('madrid', 'located_in', 'spain'),
            ('spain', 'located_in', 'europe')
        })
    ),
    Solution(
        {'country': 'spain', 'city': 'valencia'},
        derived_from=frozenset({
            ('valencia', 'located_in', 'spain'),
            ('spain', 'located_in', 'europe')
        })
    )
]
```

PS: The results are never in a praticular oder, so these assertions can fail
but they will contain the same information.

## Inference rules

You can also configure inference rules to help you define relations that are
inferred from existing facts. This is of helpful if you are trying to query
complicated relations betwen nodes. Let's take a look.

First configure your inference rules in the `settings.py` file:

```python
from triplets import Var, rule

TRIPLETS_INFERENCE_RULES = [
    rule(
        [(Var("X"), "located_in", Var("Y"))],
        implies=[(Var("X"), "part_of", Var("Y"))]
    ),
    rule(
        [(Var("X"), "part_of", Var("Y")), (Var("Y"), "part_of", Var("Z"))],
        implies=[(Var("X"), "part_of", Var("Z"))]
    )
]
```

After changing the inference rules, you need to run at least one of these:

- Run the db migrations of your project with: `python manage.py migrate`
- Run refresh migrations: `python manage.py refresh_inference`
- Call the `fact.api.refresh_inference()` function

Then these rules will generate new facts, so now you can ask for all the places
that are _part_of_ _europe_:

```python
answers = api.solve([(Var("place"), "part_of", "europe")])
assert answers == [
    {'place': 'germany'},
    {'place': 'berlin'},
    {'place': 'mitte'},
    {'place': 'spandau'},
    {'place': 'france'},
    {'place': 'paris'},
    {'place': 'spain'},
    {'place': 'madrid'},
    {'place': 'valencia'},
]
```

### Mutations when having inference rules

You can't delete inferred facts, so this will fail:

```python
api.remove(("berlin", "part_of", "germany"))
>>> ValueError("You can't remove inferred facts")
```

...and this will work:

```python
api.remove(("berlin", "located_in", "germany"))
```

And it will propagate through the inferred facts; so "berlin", "spandau" and
"mitte" will be no longer _part_of_ _germany_:

```python
answers = api.solve([(Var("place"), "part_of", "europe")])
assert answers == [
    {'place': 'germany'},
    {'place': 'france'},
    {'place': 'paris'},
    {'place': 'spain'},
    {'place': 'madrid'},
    {'place': 'valencia'},
]
```

You can restore the relation and it will regenerate the _part_of_ relations.

```python
api.add(("berlin", "located_in", "germany"))
answers = api.solve([(Var("place"), "part_of", "europe")])
assert answers == [
    {'place': 'germany'},
    {'place': 'berlin'},
    {'place': 'mitte'},
    {'place': 'spandau'},
    {'place': 'france'},
    {'place': 'paris'},
    {'place': 'spain'},
    {'place': 'madrid'},
    {'place': 'valencia'},
]
```

That's it!

## Disclaimer about this Implementation

- The query language is not recursive, so we can ensure termination. If you want
  to do complex recursive queries use inference rules.
- Don't worry about optimizing your queries, the system will do it for you.
- This is a Django specific implementation but inside `triplets.core` module is
  the logic that can be reused for any database as backend system.
- Answers to queries are not in any particular order, they are given as found in
  the database.
- The verb in a Predicate is always a string, it can't be a variable.
- Adding or Removing Facts is heavy when you have inference rules in place.
- In case you want to add many facts you can reduce the amount of work the
  engine has to do by using `triplets.api.bulk_add(t.Sequence[core.Fact])`.
- This implementation is fast at reading doing just N queries to the database,
  being N the amount of predicates you pass to `triplets.api.solve()` or
  `triplets.api.explain_solutions()`.

## TODO

- Add cardinality
    - An attribute has cardinality, name, data type
    - Operations on attributes with cardinality one perform a (x, y, Any) remove operations and then the actual add operation (x, y, z)

- Add data types:
    - Entity expression that is always about strings
    - There is like an untyped level Expressions that with the support of attribute types compile to their specific type
    - When evaluating a Predicate the predicate can optimize the queries
        - Make sure all variables with same name are of the same type

- Add different kinds of operators to constrain a query
    - Make sure all expressions make sense with the type
    - Unify all variable constrains:
        If somewhere a variable says x > 1 and somewhere x < 5, that compiles everywhere to 1 < x < 5
        Keep in mind that some variables will be in operations to other variables like in the case:
            (LittelBrother, age, LBAge)
            (BigBrother, age, LBAge < LGAge) =>
            (LittleBrother, is_little_brother_of, BigBrother)
        In this case the variables most be of the same type, and the second query can't be performed until
        the first one is not cleared out
        This case is hard to optimize for bulk operations, it will require a lookup per result in the first query.

    - Find non-sense things like 5 > x < 1
        - And respond that this is not valid and the response should be 0
