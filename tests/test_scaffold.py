"""Scaffold sanity test: package layout exists and stays importable.

Implements kickoff scaffold (pytest smoke check).
"""

import searchy


def test_package_imports() -> None:
    assert searchy.__doc__ is not None