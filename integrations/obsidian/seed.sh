#!/usr/bin/env bash
# minder-memory — Obsidian vault seeder.
#
# Idempotently seeds Obsidian configuration for the Minder Memory vault. Run by
# integrations/claude-code/install.sh after Claude integration is wired,
# but also safe to run standalone.
#
# Behaviour:
#   - If <vault>/.obsidian/ does not exist, copies vault-config/ there.
#   - If <vault>/minder-memory.md does not exist, copies the dashboard
#     template there. A dashboard under one of its earlier names —
#     <vault>/minder-ztn.md or <vault>/HOME.md — is renamed to  # rebrand:keep
#     minder-memory.md preserving any owner edits, and the vault-config
#     entries that name the dashboard file (bookmarks, ignore filter,
#     workspace) are pointed at the new name.
#     Those two are the owner's once they exist: the seeder leaves them
#     alone, and only --force overwrites them.
#   - The four help docs under <vault>/5_meta/help/ are the exception,
#     because they are not the owner's: they are copies of engine docs.
#     They are DERIVED — regenerated on every run, so a hand edit in them
#     is undone by the next one, and --force is not needed to refresh
#     them. `--refresh-help` runs that step alone; sync_engine.sh calls it
#     after every update, so a changed engine doc reaches the vault
#     instead of freezing at install time.
#
# Engine improvements to vault-config flow to friends via sync_engine.sh
# (the source under integrations/obsidian/ is engine-synced); the live
# .obsidian/ in the friend's vault stays the friend's own.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VAULT="${MINDER_MEMORY_BASE:-$REPO_ROOT/zettelkasten}"

FORCE=0
RESET_GRAPH=0
REFRESH_HELP_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --reset-graph) RESET_GRAPH=1 ;;
    --refresh-help) REFRESH_HELP_ONLY=1 ;;
    --vault) VAULT="$2"; shift ;;
    -h|--help)
      sed -n '2,22p' "$0"
      echo
      echo "Usage: $0 [--force] [--reset-graph] [--refresh-help] [--vault PATH]"
      echo
      echo "  --force        wipe and re-seed everything (with backup)"
      echo "  --refresh-help re-render <vault>/5_meta/help/ from the engine"
      echo "                 docs and do nothing else (they are DERIVED)"
      echo "  --reset-graph  restore graph.json defaults only (color groups,"
      echo "                 forces, default filter) — useful after Obsidian"
      echo "                 erased your color groups when you tweaked filters"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

log() { printf '[obsidian] %s\n' "$*"; }

# --- Help docs into the vault (DERIVED) ---
# Obsidian resolves links relative to the vault root. Engine docs live outside
# the vault (in repo `docs/` and `integrations/obsidian/`), so a curated subset
# is rendered into `<vault>/5_meta/help/` for the dashboard and bookmarks to
# link to.
#
# These four are DERIVED surfaces in the engine's own sense: copies of engine
# docs with no legitimate owner edit, regenerated on every run. They were
# previously copy-if-missing, which froze each friend's copy at the moment
# they installed — silently, since a stale doc looks exactly like a current
# one. A hand edit here is undone by the next run; that is the DERIVED rule,
# and softening it for these files would restore the freeze.
refresh_help() {
  # Validate the target BEFORE creating anything. `--refresh-help` runs from
  # the updater, which inherits MINDER_MEMORY_BASE from whatever environment it
  # was launched in; an `mkdir -p` on an unvalidated path would happily build
  # and populate a directory tree somewhere unrelated.
  if [ ! -d "$VAULT/_system" ]; then
    log "help: $VAULT is not a Minder Memory base (no _system/) — refusing to write there"
    return 1
  fi
  help_dst="$VAULT/5_meta/help"
  mkdir -p "$help_dst"
  # bash 3.2: no associative arrays. `src|dst` pairs, split below.
  help_pairs="$SCRIPT_DIR/guide.md|$help_dst/guide.md
$SCRIPT_DIR/views.md|$help_dst/views.md
$REPO_ROOT/docs/privacy.md|$help_dst/privacy.md
$REPO_ROOT/docs/CHANGELOG.md|$help_dst/CHANGELOG.md"
  while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    [ -f "$src" ] || continue
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
      log "help: $(basename "$dst") up to date"
      continue
    fi
    # Temp + rename: `cp` truncates the destination first, so a crash mid-copy
    # leaves a half-written doc that looks present. `mv` within one filesystem
    # is atomic on all three platforms. The temp name carries the pid because
    # an install, an update and a manual run can overlap — a fixed `.tmp` lets
    # one process rename a file another is still writing.
    tmp="$dst.tmp.$$"
    trap 'rm -f "$tmp"' EXIT
    cp "$src" "$tmp" && mv "$tmp" "$dst"
    trap - EXIT
    log "help: refreshed $(basename "$dst")"
  done <<HELP_PAIRS
$help_pairs
HELP_PAIRS
}

# `--refresh-help` is the narrow entry point /minder:mem:update calls: the DERIVED
# help docs and nothing else — no `.obsidian/`, no dashboard, no plugin check.
if [ "$REFRESH_HELP_ONLY" -eq 1 ]; then
  refresh_help
  exit 0
fi


if [ ! -d "$VAULT" ]; then
  echo "error: vault directory not found: $VAULT" >&2
  exit 2
fi

# --- Targeted reset: graph.json only ---
# Useful when Obsidian wiped color groups / forces during filter tweaks.
# Backs up the existing graph.json before overwrite.
if [ "$RESET_GRAPH" -eq 1 ]; then
  GRAPH_DST="$VAULT/.obsidian/graph.json"
  GRAPH_SRC="$SCRIPT_DIR/vault-config/graph.json"
  GRAPH_DEFAULTS="$VAULT/.obsidian/graph-defaults.json"
  if [ ! -f "$GRAPH_SRC" ]; then
    echo "error: source graph.json missing at $GRAPH_SRC" >&2
    exit 2
  fi
  if [ -f "$GRAPH_DST" ]; then
    cp "$GRAPH_DST" "$GRAPH_DST.bak-$(date +%Y%m%d-%H%M%S)"
    log "backed up current graph.json"
  fi
  cp "$GRAPH_SRC" "$GRAPH_DST"
  cp "$GRAPH_SRC" "$GRAPH_DEFAULTS"
  log "reset graph.json — color groups, forces, default filter restored"
  log "  reload Obsidian (Cmd+P → Reload app without saving) to pick up"
  log "  (in-vault Reset Graph button reads from .obsidian/graph-defaults.json)"
  exit 0
fi

OBS_DST="$VAULT/.obsidian"
OBS_SRC="$SCRIPT_DIR/vault-config"
DASHBOARD_DST="$VAULT/minder-memory.md"
DASHBOARD_SRC="$SCRIPT_DIR/minder-memory.template.md"

# The dashboard's earlier names, newest first. A vault that still carries one
# of them and not the current name gets the file renamed — the owner's edits
# travel with it — and the vault-config entries that name the dashboard by
# file name are pointed at the new one. Idempotent: once the current name
# exists nothing here runs again.
LEGACY_DASHBOARDS="minder-ztn.md HOME.md"  # rebrand:keep — former names, on purpose
if [ ! -f "$DASHBOARD_DST" ]; then
  for legacy_file in $LEGACY_DASHBOARDS; do
    legacy="$VAULT/$legacy_file"
    [ -f "$legacy" ] || continue
    mv "$legacy" "$DASHBOARD_DST"
    log "renamed $legacy_file -> minder-memory.md (preserved your edits)"
    # What to rewrite in the vault config depends on the former name: the
    # product slug is unambiguous anywhere it appears; `HOME` is not, so only
    # the file reference moves.
    case "$legacy_file" in
      # A blind product-slug substitution over the vault config rewrote
      # `"vaultName": "minder-ztn-иванов"` — the owner's own vault, renamed to
      # something that does not exist, in the file Obsidian reads at startup.
      # The rename map knows which names are the engine's; the sed does not, so
      # the map does this edit when it is present. The fallback is deliberately
      # narrower than the old sed rather than equal to it: the exact dashboard
      # file name, with a boundary after, and nothing else.
      minder-ztn.md) sed_expr='s/minder-ztn\.md/minder-memory.md/g'; use_map=1 ;;  # rebrand:keep
      HOME.md) sed_expr='s/HOME\.md/minder-memory.md/g'; use_map=0 ;;
      *) sed_expr=''; use_map=0 ;;
    esac
    [ -n "$sed_expr" ] || break
    for cfg in bookmarks.json app.json workspace.json; do
      cfg_path="$VAULT/.obsidian/$cfg"
      [ -f "$cfg_path" ] || continue
      if grep -q "${legacy_file%.md}" "$cfg_path"; then
        if [ "$use_map" = 1 ] && \
           [ -f "$REPO_ROOT/scripts/migrations/_032_minder_memory_rebrand.py" ]; then
          python3 "$REPO_ROOT/scripts/lib/rebrand_file.py" "$cfg_path" \
            || log "warning: could not rewrite .obsidian/$cfg — left as it was"
        else
          # `sed -i.bak` is the one form that works on both GNU and BSD sed.
          sed -i.bak "$sed_expr" "$cfg_path" && rm -f "$cfg_path.bak"
        fi
        log "pointed .obsidian/$cfg at minder-memory.md"
      fi
    done
    break
  done
fi

# --- .obsidian/ seed ---
if [ -d "$OBS_DST" ] && [ "$FORCE" -ne 1 ]; then
  log "skipped .obsidian/ — already exists at $OBS_DST"
  log "  (run with --force to overwrite — your customisations will be lost)"
else
  if [ "$FORCE" -eq 1 ] && [ -d "$OBS_DST" ]; then
    BACKUP="$VAULT/.obsidian.backup-$(date +%Y%m%d-%H%M%S)"
    mv "$OBS_DST" "$BACKUP"
    log "force: backed up existing .obsidian/ to $BACKUP"
  fi
  mkdir -p "$OBS_DST"
  # Copy entire vault-config tree (top-level *.json + snippets/, plugins/
  # if/when we add bundled plugin configs). Shell glob with `cp -R` mirrors
  # the directory structure under .obsidian/.
  for entry in "$OBS_SRC"/*; do
    [ -e "$entry" ] || continue
    cp -R "$entry" "$OBS_DST/"
  done
  log "seeded .obsidian/ at $OBS_DST"
fi

# --- Always-refresh: graph defaults snapshot ---
# minder-memory.md ships a "Reset graph" button that reads this file and
# copies it to .obsidian/graph.json. Refresh on every seed run (not
# only on full reseed) so engine improvements to graph defaults reach
# the in-vault button without requiring --force.
if [ -f "$OBS_SRC/graph.json" ] && [ -d "$OBS_DST" ]; then
  cp "$OBS_SRC/graph.json" "$OBS_DST/graph-defaults.json"
fi

# --- minder-memory.md seed ---
if [ -f "$DASHBOARD_DST" ] && [ "$FORCE" -ne 1 ]; then
  log "skipped minder-memory.md — already exists at $DASHBOARD_DST"
else
  cp "$DASHBOARD_SRC" "$DASHBOARD_DST"
  log "seeded minder-memory.md at $DASHBOARD_DST"
fi

# --- Help docs into the vault (DERIVED — see refresh_help above) ---
# Tolerant here: a seed run that cannot write help docs should still finish the
# rest. `--refresh-help` above is the strict path, because there the refresh IS
# the job and a silent no-op would be recorded as success.
refresh_help || log "help: refresh skipped"

# --- Community plugins — detect missing and warn ---
# Plugin IDs in community-plugins.json auto-enable when their main.js lands
# under .obsidian/plugins/<id>/. Until then, the dashboard's [live] blocks
# in minder-memory.md render as code.
RECOMMENDED_PLUGINS=("dataview" "obsidian-tasks-plugin" "obsidian-front-matter-title-plugin")
MISSING_PLUGINS=()
for pid in "${RECOMMENDED_PLUGINS[@]}"; do
  if [ ! -f "$OBS_DST/plugins/$pid/main.js" ]; then
    MISSING_PLUGINS+=("$pid")
  fi
done

cat <<EOF

[obsidian] done.

Open the vault in Obsidian:
  Obsidian → Open folder as vault → $VAULT

Start at minder-memory.md (Cmd+O → "minder-memory").
EOF

if [ ${#MISSING_PLUGINS[@]} -gt 0 ]; then
  cat <<EOF

[obsidian] Recommended community plugins not yet installed:
EOF
  for pid in "${MISSING_PLUGINS[@]}"; do
    case "$pid" in
      dataview) desc='Browse → search "Dataview" by Michael Brenan (NB: Settings → Dataview → enable JavaScript Queries)' ;;
      obsidian-tasks-plugin) desc='Browse → search "Tasks" by Clare Macrae' ;;
      obsidian-front-matter-title-plugin) desc='Browse → search "Front Matter Title" by snezhig (NB: enable Features after install)' ;;
      *) desc="" ;;
    esac
    printf '  - %-25s %s\n' "$pid" "$desc"
  done
  cat <<EOF

Install them in one pass:
  Obsidian → Settings → Community plugins → Turn on community plugins
  → Browse → search by author/name above → Install + Enable

(Once installed, they auto-enable on next launch — your
community-plugins.json already lists their IDs.)

File explorer cleanup is handled by the shipped CSS snippet
"minder-memory-hide-engine-paths" — already enabled by the seeder via
appearance.json. No plugin needed.

Full guide: docs/obsidian.md
EOF
fi

cat <<EOF

Settings preserved on next sync; re-run with --force only if you want
to reset .obsidian/ and minder-memory.md to engine defaults.
EOF
