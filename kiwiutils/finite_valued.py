"""
This module contains utilities related to finite-valued types.
"""

from typing import (
    TypeVar,
    Callable,
    Generator,
    Iterable,
    Union,
    get_origin,
    get_args,
    Literal,
)
from types import UnionType
from functools import cache, wraps
from dataclasses import Field
import itertools

import enum
import frozendict

from kiwiutils.kiwilib import IsDataclass, flatten, is_abstract

"""
# `FiniteValued`
The details of this type are not possible to fully define via the Python 3.10 typing library.
This custom generic type is a generic domain of many types which have a finite, discrete, and well-defined range space.
`FiniteValued` defines the domain of supported types for the `all_instances` function, since that function relies heavily on static typing. 
These types may be nested in an arbitrarily deep tree via Container Types and Superclass Types (see below).
The leaves of the tree must always be Primitive Types. 

# `FiniteValued` Subtypes
*: Indicates that this subtype is not yet supported by `all_instances`

## Non-`FiniteValued` (Unbounded) Types
These are NOT valid subtypes, and are listed for illustrative purposes only.
This list is not comprehensive.
While the finite and discrete nature of digital computers means that the cardinality of these types is technically finite, 
they are considered unbounded types in this context.
- No Container subtype may contain any of these unbounded subtypes.
- `int`
- `float`
- `str`
- `list`
- `set`: Set types without a `FiniteValued` argument are unbounded
- `tuple`: Tuple types without a fixed length are unbounded

## Primitive Types
Primitive types are non-nested types which resolve directly to a concrete range of values 
- `bool`: has 2 possible values
- *`enum.Enum`: The range of a concrete `Enum` subclass is its set of enum members
- `typing.Literal`: Every type constructed using `Literal` has a finite set of possible literal values in its definition.
This is the preferred way to include limited ranges of non-`FiniteValued` types such as `int` or `str` in a `FiniteValued` hierarchy.

## Container Types
Container types are types which contain zero or more fields of `FiniteValued` type.
The range of a container type is the cartesian product of their field types, except for `set[FiniteValued]`.
- `tuple[FiniteValued]`: Tuples of fixed length whose elements are each `FiniteValued`.
- `IsDataclass`: Concrete dataclasses whose fields are `FiniteValued`.
- *Standard concrete class: Regular classes could be supported just like dataclasses if all their data members are `FiniteValued`-typed.
- *`set[FiniteValued]`: Sets of fixed length of a `FiniteValued` type.

## Superclass Types
Superclass types don't directly contain data members like container types.
Their range is the union of the ranges of their subtypes.
- Abstract dataclasses: Abstract dataclasses whose subclasses are all `FiniteValued` superclass or container types
- *`IsDataclass`: Concrete dataclasses which also have their own subclasses.
- *Standard abstract classes: Abstract dataclasses whose subclasses are all `FiniteValued` superclass or container types
- `UnionType`: Any union of `FiniteValued` types, e.g., bool | Literal[2, 3]
"""
FiniteValued = TypeVar("FiniteValued", bound=bool | IsDataclass | enum.Enum)


def _apply_validation_func(
    type_: FiniteValued,
    vals: Generator[FiniteValued, None, None],
    validation_funcs: (
        frozendict.frozendict[FiniteValued, Callable[[FiniteValued], bool]] | None
    ) = None,
) -> Generator[FiniteValued, None, None]:
    """
    Helper function for `all_instances`.
    Filters `vals` according to `validation_funcs`.
    If `type_` is a regular type, searches in MRO order in `validation_funcs` and applies the first match, if any.
    Handles generic types supported by `all_instances` with special `if` clauses.

    # Parameters
    - `type_: FiniteValued`: A type
    - `vals: Generator[FiniteValued, None, None]`: Instances of `type_`
    - `validation_funcs: dict`: Collection of types mapped to filtering validation functions
    """
    if validation_funcs is None:
        return vals
    if type_ in validation_funcs:  # Only possible catch of UnionTypes
        return filter(validation_funcs[type_], vals)
    elif hasattr(
        type_, "__mro__"
    ):  # Generic types like UnionType, Literal don't have `__mro__`
        for superclass in type_.__mro__:
            if superclass not in validation_funcs:
                continue
            vals = filter(validation_funcs[superclass], vals)
            break  # Only the first validation function hit in the mro is applied
    elif get_origin(type_) == Literal:
        return flatten(
            (
                _apply_validation_func(type(v), [v], validation_funcs)
                for v in get_args(type_)
            ),
            levels_to_flatten=1,
        )
    return vals


def _all_instances_wrapper(f):
    """
    Converts dicts to frozendicts to allow caching and applies `_apply_validation_func`.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        @cache
        def cached_wrapper(
            type_: type,
            all_instances_func: Callable,
            validation_funcs: (
                frozendict.frozendict[FiniteValued, Callable[[FiniteValued], bool]]
                | None
            ),
        ):
            return _apply_validation_func(
                type_, all_instances_func(type_, validation_funcs), validation_funcs
            )

        if len(args) >= 2 and args[1] is not None:
            validation_funcs: frozendict.frozendict = frozendict.frozendict(args[1])
        elif "validation_funcs" in kwargs and kwargs["validation_funcs"] is not None:
            validation_funcs: frozendict.frozendict = frozendict.frozendict(
                kwargs["validation_funcs"]
            )
        else:
            validation_funcs = None
        return cached_wrapper(args[0], f, validation_funcs)

    return wrapper


@_all_instances_wrapper
def all_instances(
    type_: FiniteValued,
    validation_funcs: dict[FiniteValued, Callable[[FiniteValued], bool]] | None = None,
) -> Generator[FiniteValued, None, None]:
    """
    Returns all possible values of an instance of `type_` if finite instances exist.
    Uses type hinting to construct the possible values.
    All nested elements of `type_` must themselves be typed.
    Do not use with types whose members contain circular references.
    Function is susceptible to infinite recursion if `type_` is a dataclass whose member tree includes another instance of `type_`.

    # Parameters
    - `type_: FiniteValued`
        A finite-valued type. See docstring on `FiniteValued` for full details.
    - `validation_funcs: dict[FiniteValued, Callable[[FiniteValued], bool]] | None`
        A mapping of types to auxiliary functions to validate instances of that type.
        This optional argument can provide an additional, more precise layer of validation for the instances generated beyond what type hinting alone can provide.
        See `validation_funcs` Details section below.
        (default: `None`)

    ## Supported `type_` Values
    See docstring on `FiniteValued` for full details.
    `type_` may be:
    - `FiniteValued`
    - A finite-valued, fixed-length Generic tuple type.
    E.g., `tuple[bool]`, `tuple[bool, MyEnum]` are OK.
    `tuple[bool, ...]` is NOT supported, since the length of the tuple is not fixed.
    - Nested versions of any of the types in this list
    - A `UnionType` of any of the types in this list

    ## `validation_funcs` Details
    - `validation_funcs` is applied after all instances have been generated according to type hints.
    - If `type_` is in `validation_funcs`, then the list of instances is filtered by `validation_funcs[type_](instance)`.
    - `validation_funcs` is passed down for all recursive calls of `all_instances`.
    - This allows for improved performance through maximal pruning of the exponential tree.
    - `validation_funcs` supports subclass checking.
    - If `type_` is not found in `validation_funcs`, then the search is performed iteratively in mro order.
    - If a superclass of `type_` is found while searching in mro order, that validation function is applied and the list is returned.
    - If no superclass of `type_` is found, then no filter is applied.
    """
    if type_ == bool:
        yield from [True, False]
    elif hasattr(type_, "__dataclass_fields__"):
        if is_abstract(type_):
            # Abstract dataclass: call `all_instances` on each subclass
            yield from flatten(
                (
                    all_instances(sub, validation_funcs)
                    for sub in type_.__subclasses__()
                ),
                levels_to_flatten=1,
            )
        else:
            # Concrete dataclass: construct dataclass instances with all possible combinations of fields
            fields: list[Field] = type_.__dataclass_fields__
            fields_to_types: dict[str, type] = {f: fields[f].type for f in fields}
            all_arg_sequences: Iterable = itertools.product(
                *[
                    all_instances(arg_type, validation_funcs)
                    for arg_type in fields_to_types.values()
                ]
            )
            yield from (
                type_(**{fld: arg for fld, arg in zip(fields_to_types.keys(), args)})
                for args in all_arg_sequences
            )
    else:
        type_origin = get_origin(type_)
        if type_origin == tuple:
            # Only matches Generic type tuple since regular tuple is not finite-valued
            # Generic tuple: Similar to concrete dataclass. Construct all possible combinations of tuple fields.
            yield from (
                tuple(combo)
                for combo in itertools.product(
                    *(
                        all_instances(tup_item, validation_funcs)
                        for tup_item in get_args(type_)
                    )
                )
            )
        elif type_origin in (UnionType, Union):
            # Union: call `all_instances` for each type in the Union
            yield from flatten(
                [all_instances(sub, validation_funcs) for sub in get_args(type_)],
                levels_to_flatten=1,
            )
        elif type_origin is Literal:
            # Literal: return all Literal arguments
            yield from get_args(type_)
        else:
            raise TypeError(
                f"Type {type_} either has unbounded possible values or is not supported (Enum is not supported)."
            )
