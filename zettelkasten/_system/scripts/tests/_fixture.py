"""Fixture builder for tests — synthesises a temporary Minder Memory base on disk."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


VALID_NOTE = """---
id: axiom-identity-001
title: If it can be better, it should be better
type: axiom
domain: identity
statement: >
  Choose the higher-quality path when the system is likely to outlive
  this decision.
priority_tier: 1
framing: positive
binding: hard
core: true
scope: shared
applies_to: [claude-code, minder-memory]
derived_from: []
contradicts: []
confidence: proven
status: active
created: 2026-01-01
last_reviewed: 2026-01-01
last_applied: null
source_weight:
  own_experience: 5
  external_author: 0
---

# If it can be better, it should be better

## Statement
Choose the higher-quality path.

## Evidence Trail
- **2026-01-01** | landing | — seeded for test
"""


VALID_PERSONAL_NOTE = """---
id: principle-tech-001
title: Prefer clarity over cleverness
type: principle
domain: tech
statement: Clarity beats cleverness in code.
priority_tier: 3
framing: positive
binding: soft
core: false
scope: personal
applies_to: [claude-code, minder-memory]
derived_from: [axiom-identity-001]
contradicts: []
confidence: working
status: active
created: 2026-01-01
last_reviewed: 2026-01-01
last_applied: null
---

# Prefer clarity over cleverness

## Statement
Clarity wins.

## Evidence Trail
- **2026-01-01** | landing | — seeded for test
"""


VALID_SENSITIVE_NOTE = """---
id: rule-health-001
title: No work email after 22:00
type: rule
domain: health
statement: Do not process work email past 22:00 local time.
priority_tier: 1
framing: negative
binding: hard
core: false
scope: sensitive
applies_to: [life-advice]
derived_from: []
contradicts: []
confidence: working
status: active
created: 2026-01-01
last_reviewed: 2026-01-01
last_applied: null
---

# No work email after 22:00

## Statement
Hard boundary.

## Evidence Trail
- **2026-01-01** | landing | — seeded for test
"""


VALID_PLACEHOLDER_CORE = """---
id: axiom-meta-001
title: Placeholder core — should be excluded from SOUL and exports
type: axiom
domain: meta
statement: Placeholder content never ships.
priority_tier: 1
framing: positive
binding: hard
core: true
scope: shared
applies_to: [claude-code]
derived_from: []
contradicts: []
confidence: experimental
status: placeholder
created: 2026-01-01
last_reviewed: 2026-01-01
last_applied: null
---

# Placeholder core

## Statement
Placeholder.

## Evidence Trail
- **2026-01-01** | landing | — seeded for test
"""


MALFORMED_YAML = """---
id: axiom-identity-002
title: Missing required field test
type: axiom
domain: identity
priority_tier: 1
scope: shared
applies_to: [claude-code]
status: active
created: 2026-01-01
---

# Oops, no statement, no title validation expected
"""


BAD_ENUM = """---
id: axiom-identity-003
title: Bad tier
type: axiom
domain: identity
statement: Test
priority_tier: 9
scope: shared
applies_to: [claude-code]
status: active
created: 2026-01-01
---

# Bad tier body
"""


BAD_ID_SHAPE = """---
id: totally-wrong-id
title: Id prefix mismatch
type: axiom
domain: identity
statement: Test
priority_tier: 1
scope: shared
applies_to: [claude-code]
status: active
created: 2026-01-01
---

# Bad id body
"""


SOUL_TEMPLATE = """---
id: soul
layer: system
---

# SOUL

## Identity

- **Name:** Test User

## Current Focus

Hand-written focus area.

<!-- AUTO-GENERATED FROM CONSTITUTION — DO NOT EDIT MANUALLY -->
<!-- placeholder content — render_soul_values.py overwrites this -->
<!-- END AUTO-GENERATED -->

## Working Style

Hand-written style area.
"""


CLARIFICATIONS_TEMPLATE = """# Clarifications Needed

**Purpose:** test fixture.

---

## Open Items

"""


@dataclass
class Fixture:
    base: Path  # zettelkasten/ root

    @property
    def constitution(self) -> Path:
        return self.base / "0_constitution"

    @property
    def system(self) -> Path:
        return self.base / "_system"

    def write_principle(self, relpath: str, content: str) -> Path:
        dest = self.constitution / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return dest

    def write_system_file(self, name: str, content: str) -> Path:
        """Write a file under `_system/`. `name` may include subdirs
        (e.g. `state/CLARIFICATIONS.md`); parents are created as needed."""
        dest = self.system / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return dest


def make_fixture(tmp_dir: Path) -> Fixture:
    base = tmp_dir / "zettelkasten"
    (base / "0_constitution").mkdir(parents=True)
    (base / "_system").mkdir(parents=True)
    os.environ["MINDER_MEMORY_BASE"] = str(base)
    return Fixture(base=base)


def clear_minder_memory_env() -> None:
    os.environ.pop("MINDER_MEMORY_BASE", None)
    os.environ.pop("CLAUDE_CONTEXT", None)
