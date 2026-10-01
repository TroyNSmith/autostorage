"""Pytest configuration."""

# Local, git-ignored scratch scripts (see .gitignore) are not tests, but
# `--doctest-modules` would otherwise import (and run) them.
collect_ignore_glob = ["scratch*"]
