from ..api import Attr, Fact, In, Var, compile_rules
from . import common

places_facts: list[Fact] = [
    # light snow
    ("winterfell", "precipitation_percent", 60),
    ("winterfell", "precipitation_mm", 1),
    ("winterfell", "temperature_c", -2),
    # heavy rain
    ("tropic", "precipitation_percent", 50),
    ("tropic", "precipitation_mm", 10),
    ("tropic", "temperature_c", 34),
    # nothing
    ("nothing1", "precipitation_mm", 60),
    ("nothing2", "precipitation_mm", 10),
    ("nothing3", "precipitation_percent", 10),
    ("nothing3", "precipitation_mm", 10),
    # place with mild temperature
    ("mild_temp", "temperature_c", 10),
]

attributes = Attr.as_dict(
    Attr("located_in", str, "one"),
    Attr("precipitation_percent", int, "one"),
    Attr("precipitation_mm", int, "one"),
    Attr("cloud_percent", int, "one"),
    Attr("temperature_c", int, "one"),
    Attr("weather_condition", str, "one"),
    Attr("is_warmer_than", str, "many"),
    Attr("is_colder_than", str, "many"),
)

will_precipitate = (
    Var("place"),
    "precipitation_percent",
    Var("precipitation") >= 50,
)
light_precipitation = (Var("place"), "precipitation_mm", Var("mm") <= 5)
heavy_precipitation = (Var("place"), "precipitation_mm", Var("mm") > 5)
cold = (Var("place"), "temperature_c", Var("temp") <= 0)
warm = (Var("place"), "temperature_c", Var("temp") > 0)


class LightSnowRule:
    predicate = [will_precipitate, light_precipitation, cold]
    implies = [(Var("place"), "weather_condition", "light snow")]


class HeavySnowRule:
    predicate = [will_precipitate, heavy_precipitation, cold]
    implies = [(Var("place"), "weather_condition", "heavy snow")]


class LightRainRule:
    predicate = [will_precipitate, light_precipitation, warm]
    implies = [(Var("place"), "weather_condition", "light rain")]


class HeavyRainRule:
    predicate = [will_precipitate, heavy_precipitation, warm]
    implies = [(Var("place"), "weather_condition", "heavy rain")]


class TemperatureRelationRule:
    predicate = [
        (Var("warm_place"), "temperature_c", Var("warm")),
        (Var("cold_place"), "temperature_c", Var("cold") < Var("warm")),
    ]
    implies = [
        (Var("warm_place"), "is_warmer_than", Var("cold_place")),
        (Var("cold_place"), "is_colder_than", Var("warm_place")),
    ]


weather_condition_rules = compile_rules(
    attributes,
    LightSnowRule,
    HeavySnowRule,
    LightRainRule,
    HeavyRainRule,
    TemperatureRelationRule,
)


class TestBooleanExpressions(common.TestUsingDjango):
    def setUp(self) -> None:
        with self.assertNumQueries(57):
            self.populate_db(attributes, places_facts, weather_condition_rules)

    def test_weather_condition_is_properly_inferred(self):
        with self.assertNumQueries(2):
            solutions = self.solve(
                [
                    ("winterfell", "weather_condition", Var("winterfell")),
                    ("tropic", "weather_condition", Var("tropic")),
                ]
            )
        self.assertSetEqual(
            solutions,
            {
                frozenset(
                    {("winterfell", "light snow"), ("tropic", "heavy rain")}
                )
            },
        )

        with self.assertNumQueries(1):
            solutions = self.solve(
                [
                    (
                        In("place", {"winterfell", "tropic"}),
                        "weather_condition",
                        Var("condition"),
                    ),
                ]
            )
        self.assertSetEqual(
            solutions,
            {
                frozenset(
                    {
                        ("place", "tropic"),
                        ("condition", "heavy rain"),
                    }
                ),
                frozenset(
                    {
                        ("place", "winterfell"),
                        ("condition", "light snow"),
                    }
                ),
            },
        )

    def test_warmer_colder_places_are_inferred_correctly(self):
        with self.assertNumQueries(1):
            solutions = self.solve(
                [(Var("cold_place"), "is_colder_than", Var("warm_place"))]
            )

        self.assertSetEqual(
            solutions,
            {
                frozenset(
                    {("warm_place", "mild_temp"), ("cold_place", "winterfell")}
                ),
                frozenset(
                    {("warm_place", "tropic"), ("cold_place", "winterfell")}
                ),
                frozenset(
                    {("warm_place", "tropic"), ("cold_place", "mild_temp")}
                ),
            },
        )

        with self.assertNumQueries(2):
            solutions = self.solve(
                [
                    (Var("warm_place"), "temperature_c", Var("warm")),
                    (
                        Var("cold_place"),
                        "temperature_c",
                        Var("warm") > Var("cold"),
                    ),
                ]
            )

        self.assertSetEqual(
            solutions,
            {
                frozenset(
                    {
                        ("cold_place", "mild_temp"),
                        ("cold", 10),
                        ("warm_place", "tropic"),
                        ("warm", 34),
                    }
                ),
                frozenset(
                    {
                        ("cold_place", "winterfell"),
                        ("cold", -2),
                        ("warm_place", "mild_temp"),
                        ("warm", 10),
                    }
                ),
                frozenset(
                    {
                        ("cold_place", "winterfell"),
                        ("cold", -2),
                        ("warm_place", "tropic"),
                        ("warm", 34),
                    }
                ),
            },
        )
