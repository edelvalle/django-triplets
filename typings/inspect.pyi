import enum
import typing as t
from collections import OrderedDict

class _ParameterKind(enum.IntEnum):
    POSITIONAL_ONLY = 0
    POSITIONAL_OR_KEYWORD = 1
    VAR_POSITIONAL = 2
    KEYWORD_ONLY = 3
    VAR_KEYWORD = 4

class Parameter:
    POSITIONAL_ONLY = _ParameterKind.POSITIONAL_ONLY
    POSITIONAL_OR_KEYWORD = _ParameterKind.POSITIONAL_OR_KEYWORD
    VAR_POSITIONAL = _ParameterKind.VAR_POSITIONAL
    KEYWORD_ONLY = _ParameterKind.KEYWORD_ONLY
    VAR_KEYWORD = _ParameterKind.VAR_KEYWORD

    empty: object

    name: str
    kind: _ParameterKind
    default: t.Any
    annotation: t.Type[object]

class Signature:
    parameters: OrderedDict[str, Parameter]

def signature(obj: t.Callable[..., t.Any]) -> Signature: ...
