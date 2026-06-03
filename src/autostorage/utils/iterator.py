"""Convenience methods for database."""

from collections.abc import Iterator
from itertools import tee

UNKNOWN = object()


def is_empty[T](iterator: Iterator[T]) -> tuple[bool, Iterator[T]]:
    """
    Check that an iterator is empty.

    Parameters
    ----------
    iterator
        Iterable sequence.

    Returns
    -------
    bool
        iterator is empty
    iterator
        Fresh copy of iterator
    """
    (iterator, it2) = tee(iterator, 2)
    e1 = next(it2, UNKNOWN)
    return e1 is UNKNOWN, iterator
