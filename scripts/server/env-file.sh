#!/usr/bin/env sh
# Read allowlisted values from a Docker Compose env file without executing it.
#
# The operational scripts intentionally accept only simple literal values for
# the keys they consume. Docker Compose supports interpolation and several
# quoting/comment forms; silently approximating those rules could make the
# preflight validate a different value from the one Compose uses.

read_env_value() {
  key="$1"
  awk -v key="$key" '
    {
      line = $0
      sub(/\r$/, "", line)
      if (line !~ "^[[:space:]]*" key "[[:space:]]*=") {
        next
      }
      sub("^[[:space:]]*" key "[[:space:]]*=[[:space:]]*", "", line)
      sub(/[[:space:]]*$/, "", line)
      value = line
      matches++
    }
    END {
      if (matches > 1) {
        exit 3
      }
      if (matches == 1) {
        print value
      }
    }
  ' "$ENV_FILE"
}

load_env_key() {
  key="$1"
  # The caller supplies literal, allowlisted names. Environment variables take
  # precedence over the file, matching Docker Compose interpolation behavior.
  eval "is_set=\${$key+x}"
  if [ "$is_set" = "x" ] || [ ! -f "$ENV_FILE" ]; then
    return 0
  fi

  if ! value=$(read_env_value "$key"); then
    printf 'Invalid %s: %s is defined more than once.\n' "$ENV_FILE" "$key" >&2
    return 1
  fi
  case "$value" in
    *'$'*|*'#'*|*'"'*|*"'"*|*'\'*)
      printf 'Invalid %s: %s must be an unquoted literal without #, $, or backslashes.\n' \
        "$ENV_FILE" "$key" >&2
      return 1
      ;;
  esac
  if [ -n "$value" ]; then
    export "$key=$value"
  fi
}

volume_root_for_path() {
  path="$1"
  case "$path" in
    /Volumes/*)
      relative=${path#/Volumes/}
      volume_name=${relative%%/*}
      [ -n "$volume_name" ] || return 1
      printf '/Volumes/%s\n' "$volume_name"
      ;;
    *) return 1 ;;
  esac
}

is_active_mountpoint() {
  expected="$1"
  [ -d "$expected" ] || return 1
  # POSIX df -P keeps each filesystem on one line. Reassemble fields 6..N so
  # volume names containing spaces are compared as a complete mount path.
  df -P "$expected" 2>/dev/null | awk -v expected="$expected" '
    NR > 1 {
      mounted = $6
      for (i = 7; i <= NF; i++) {
        mounted = mounted " " $i
      }
    }
    END { exit !(mounted == expected) }
  '
}

path_has_active_external_volume() {
  path="$1"
  if ! root=$(volume_root_for_path "$path"); then
    return 0
  fi
  is_active_mountpoint "$root"
}
