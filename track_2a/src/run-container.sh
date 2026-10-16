#!/bin/sh
# Offline only. Never source an env file or forward host credentials.
set -eu
fail() { printf '%s\n' "$1" >&2; exit 2; }
project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
repo=$(CDPATH= cd -- "$project/.." && pwd -P)
operation=${1:-demo}
case "$operation" in demo|comparison-demo|prepare|import|review|test) ;; *) fail 'Unsupported operation';; esac
uid=$(id -u)
gid=$(id -g)
[ "$uid" -ne 0 ] || fail 'Run from a non-root host account.'
image=${IMAGE:-formrehearsal-track2a-source-candidate:local}
set -- docker run --rm --pull=never --platform linux/amd64 --network=none --read-only \
  --cap-drop=ALL --security-opt=no-new-privileges:true --pids-limit=64 --memory=2g --cpus=2 \
  --user "$uid:$gid" --tmpfs /tmp:rw,noexec,nosuid,size=128m
if [ "$operation" = test ]; then
  exec "$@" "$image" test
fi
output=${OUTPUT_ROOT:-"$project/artifacts"}
mkdir -p -- "$output"
output=$(CDPATH= cd -- "$output" && pwd -P)
case "$output" in *','*|*'
'*) fail 'Mount paths cannot contain commas or newlines';; esac
case "$repo/" in "$output/"*) fail 'Output parent must not contain source code';; esac
case "$output/" in
  "$repo/"*)
    case "$output/" in "$project/artifacts/"*) ;; *) fail 'Inside the repository, output is allowed only under track_2a/artifacts';; esac
    ;;
esac
name=${OUTPUT_NAME:-"$operation"}
case "$name" in ''|.|..|*[!A-Za-z0-9._-]*) fail 'OUTPUT_NAME must be a simple filename';; esac
[ ! -e "$output/$name" ] && [ ! -L "$output/$name" ] || fail 'Output exists. Set a fresh OUTPUT_NAME; nothing is overwritten.'
set -- "$@" --mount "type=bind,src=$output,dst=/output"
check_input() {
  case "$1" in /*) ;; *) fail 'All input paths must be absolute';; esac
  case "$1" in *','*|*'
'*) fail 'Mount paths cannot contain commas or newlines';; esac
  [ ! -L "$1" ] || fail 'Top-level symlink inputs are rejected'
  case "$1/" in "$output/"*) fail 'Input must not be in the writable output mount';; esac
  case "$output/" in "$1/"*) fail 'Input must not contain the writable output mount';; esac
}
case "$operation" in
  prepare)
    pdf=${PDF:?Set PDF to an absolute existing file}
    check_input "$pdf"
    [ -f "$pdf" ] || fail 'PDF is not a regular file'
    pdf="$(CDPATH= cd -- "$(dirname -- "$pdf")" && pwd -P)/$(basename -- "$pdf")"
    check_input "$pdf"
    set -- "$@" --mount "type=bind,src=$pdf,dst=/input/source.pdf,readonly" "$image" prepare \
      --pdf /input/source.pdf --chunk-chars "${CHUNK_CHARS:-4000}" --out "/output/$name"
    ;;
  import|review)
    prepared=${PREPARED:?Set PREPARED to an absolute directory}
    check_input "$prepared"
    [ -d "$prepared" ] || fail 'PREPARED is not a directory'
    prepared=$(CDPATH= cd -- "$prepared" && pwd -P)
    check_input "$prepared"
    set -- "$@" --mount "type=bind,src=$prepared,dst=/input/prepared,readonly"
    if [ "$operation" = import ]; then
      index=${INDEX:?Set INDEX to an absolute index.json file}
      check_input "$index"
      [ -f "$index" ] || fail 'INDEX is not a regular file'
      captures=$(CDPATH= cd -- "$(dirname -- "$index")" && pwd -P)
      check_input "$captures"
      set -- "$@" --mount "type=bind,src=$captures,dst=/input/captures,readonly" "$image" import \
        --prepared /input/prepared --index "/input/captures/$(basename -- "$index")" \
        --expected-prepare "${EXPECTED_PREPARE:?Set the independently retained preparation pin}" --out "/output/$name"
    else
      imported=${IMPORTED:?Set IMPORTED to an absolute directory}
      check_input "$imported"
      [ -d "$imported" ] || fail 'IMPORTED is not a directory'
      imported=$(CDPATH= cd -- "$imported" && pwd -P)
      check_input "$imported"
      set -- "$@" --mount "type=bind,src=$imported,dst=/input/imported,readonly" "$image" review \
        --prepared /input/prepared --imported /input/imported \
        --expected-import "${EXPECTED_IMPORT:?Set the independently retained import pin}" --out "/output/$name"
    fi
    ;;
  *) set -- "$@" "$image" "$operation" --out "/output/$name" ;;
esac
exec "$@"
