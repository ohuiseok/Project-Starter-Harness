#!/usr/bin/env bash
# Shared helpers for Project Starter Harness scripts.
# Source this file; do not run it directly.
#
# Exit codes used by all scripts:
#   0  confirmed
#   1  confirmed negative (target missing, tests failed)
#   2  usage error
#   3  cannot verify (UNKNOWN)

EXIT_UNKNOWN=3

HARNESS_LIB_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HARNESS_ROOT="$(CDPATH= cd -- "$HARNESS_LIB_DIR/../.." && pwd -P)"

usage() {
  printf 'Usage: %s --target PATH\n' "$0" >&2
}

# Parse arguments into TARGET. Falls back to $TARGET_REPOSITORY.
parse_target_args() {
  TARGET="${TARGET_REPOSITORY:-}"

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --target)
        if [ "$#" -lt 2 ]; then
          printf 'UNKNOWN: --target requires a value\n' >&2
          exit 2
        fi
        TARGET="$2"
        shift 2
        ;;
      --target=*)
        TARGET="${1#--target=}"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        printf 'UNKNOWN: unsupported argument: %s\n' "$1" >&2
        exit 2
        ;;
    esac
  done

  resolve_target_from_config
}

# Guard for "--flag VALUE" parsing. Without it, `shift 2` with a single
# argument left fails, $# never reaches zero, and the caller's loop spins
# forever. Call as: need_value "$1" "$#"
need_value() {
  if [ "$2" -lt 2 ]; then
    printf 'UNKNOWN: %s requires a value\n' "$1" >&2
    exit 2
  fi
}

# Read a "key: value" pair from config/target.local.yaml.
read_config_value() {
  local key="$1" config="$HARNESS_ROOT/config/target.local.yaml"

  [ -f "$config" ] || return 1
  sed -n "s/^[[:space:]]*$key:[[:space:]]*//p" "$config" | head -n 1
}

# Fall back to config/target.local.yaml when no path was given.
resolve_target_from_config() {
  [ -z "$TARGET" ] || return 0
  TARGET="$(read_config_value repository || true)"
}

require_commands() {
  local command_name

  for command_name in "$@"; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      printf 'UNKNOWN: %s is not available\n' "$command_name" >&2
      exit 2
    fi
  done
}

# Resolve TARGET to the target repository's Git root in TARGET_ROOT.
require_target_git_root() {
  if [ -z "$TARGET" ] || [ ! -d "$TARGET" ]; then
    printf 'UNKNOWN: target repository path is invalid\n' >&2
    exit 2
  fi

  TARGET_ROOT="$(CDPATH= cd -- "$TARGET" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)" || {
    printf 'UNKNOWN: target is not a git repository\n' >&2
    exit 2
  }
  TARGET_ROOT="$(CDPATH= cd -- "$TARGET_ROOT" && pwd -P)"

  if [ "$TARGET_ROOT" = "$HARNESS_ROOT" ]; then
    printf 'UNKNOWN: target repository must not be the harness repository\n' >&2
    exit 2
  fi
}

# Require TARGET to be an existing directory and set TARGET_ABS.
require_target_dir() {
  if [ -z "$TARGET" ] || [ ! -d "$TARGET" ]; then
    printf 'UNKNOWN: target path is invalid\n' >&2
    exit 2
  fi

  TARGET_ABS="$(CDPATH= cd -- "$TARGET" 2>/dev/null && pwd -P)" || {
    printf 'UNKNOWN: target path is invalid\n' >&2
    exit 2
  }
}

# Print the build file name found in $1, or nothing.
detect_build_file() {
  local root="$1" name
  for name in build.gradle build.gradle.kts pom.xml; do
    if [ -f "$root/$name" ]; then
      printf '%s' "$name"
      return 0
    fi
  done
  return 1
}

# True when $1 holds JVM sources under the standard layout.
has_jvm_sources() {
  [ -d "$1/src/main/java" ] || [ -d "$1/src/main/kotlin" ]
}
