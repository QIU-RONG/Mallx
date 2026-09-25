# -*- coding: utf-8 -*-
"""Portable path resolution for the loadtest suite.

Background
----------
These scripts hard-coded absolute Windows paths (``D:\\MallX\\backend\\...``) because they
were written on one machine. That is fine locally, but it makes the suite unrunnable on a
Linux CI runner: such a literal is not an absolute path there -- it is a single *filename*
containing backslashes. So reads fail (``FileNotFoundError``) and reports land in a file
literally named ``D:\\MallX\\...``.

``lp()`` keeps every legacy literal working unchanged while making the suite
location-independent: the ``D:\\MallX\\`` prefix is stripped and the remainder is rejoined
against the repository root derived from this file's own location.

    lp(r"D:\\MallX\\backend\\sql\\01-schema.sql")
        -> "<repo>/backend/sql/01-schema.sql"      (on any OS)

Rotation rule
-------------
New code should build paths from ``REPO_ROOT`` / ``LOADTEST_DIR`` directly.
``lp()`` exists only to migrate the legacy literals without a 71-site hand edit; it is a
migration shim, not a convention to copy.

Why a module instead of a copy-pasted helper
--------------------------------------------
There were 71 call sites across 29 files. Inlining a 5-line resolver into each file would
have cost ~150 lines of duplicated logic -- i.e. it would have created exactly the kind of
"same rule, many copies" drift this project already has a judgment call about (cf. the
T1 ``MAX_PAGE_SIZE`` entry in ``docs/backlog.md``). One definition, no drift.

Import note: scripts are run as ``python backend/loadtest/dayNN-*.py`` (or from inside
``backend/loadtest``), so Python puts this directory on ``sys.path`` and
``from _paths import lp`` resolves.
"""
import os
import re

LOADTEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(LOADTEST_DIR))

_LEGACY_RX = re.compile(r"^[A-Za-z]:[\\/]MallX[\\/]")


def lp(legacy):
    """Rewrite a legacy ``D:\\MallX\\...`` absolute path against this checkout."""
    rel = _LEGACY_RX.sub("", legacy).replace("\\", "/")
    return os.path.join(REPO_ROOT, rel)
