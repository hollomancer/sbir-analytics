#!/usr/bin/env bash
#
# collect_local_diagnostics.sh
#
# Collect a broad set of local diagnostics (CPU, memory, IO, disk, Docker, Python process samples)
# and write them into a timestamped directory under ./reports/diagnostics-local/<timestamp>/
#
# Usage:
#   chmod +x sbir-analytics/scripts/collect_local_diagnostics.sh
#   ./sbir-analytics/scripts/collect_local_diagnostics.sh [optional-output-dir]
#
# Notes:
# - Designed to run on macOS or Linux. It will detect available utilities and skip those that aren't present.
# - For Python process sampling it prefers `py-spy` (no install required if already present).
#   On macOS it will use `sample` if available as a fallback.
# - Outputs are plain-text files and optional flamegraph (py-spy) SVGs if py-spy is available.
# - Final archive is created as a .tar.gz in the selected output directory.
#
set -uo pipefail

# Allow the user to override the base output directory (defaults to repository-relative reports/)
BASE_OUT_DIR="${1:-reports/diagnostics-local}"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
OUT_DIR="${BASE_OUT_DIR}/${TIMESTAMP}"
mkdir -p "${OUT_DIR}"

# Helper: run a command and save stdout/stderr to a file (avoid exiting on failure)
run_capture() {
  local outfile="$1"; shift
  echo "+ $*" > "${OUT_DIR}/${outfile}.cmd"
  # Run the command, capture both stdout and stderr
  { "$@" ; } > "${OUT_DIR}/${outfile}.out" 2> "${OUT_DIR}/${outfile}.err" || true
}

# Helper: run a command if it exists
run_if_exists() {
  local cmd="$1"; shift
  if command -v "${cmd}" >/dev/null 2>&1; then
    "$@"
  else
    echo "skipping ${cmd} (not installed)" > "${OUT_DIR}/SKIPPED_${cmd}.txt"
  fi
}

echo "Collecting diagnostics into: ${OUT_DIR}"
echo "Start time (UTC): $(date -u)" > "${OUT_DIR}/collection_meta.txt"
uname -a >> "${OUT_DIR}/collection_meta.txt" 2>&1 || true
echo "Uptime:" >> "${OUT_DIR}/collection_meta.txt"
uptime >> "${OUT_DIR}/collection_meta.txt" 2>&1 || true

# Basic process snapshots
run_capture "ps_cpu_top" ps aux --sort=-%cpu | head -n 50
run_capture "ps_mem_top" ps aux --sort=-rss | head -n 50

# Per-user process count summary
run_capture "ps_users_summary" ps aux | awk '{print $1}' | sort | uniq -c | sort -rn

# Basic system metrics
run_capture "df_h" df -h
run_capture "mount" mount || run_capture "mount" /sbin/mount

# Platform-specific memory / vm stats
OS_NAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
if [[ "${OS_NAME}" == "darwin" ]]; then
  # macOS
  run_capture "vm_stat" vm_stat
  run_capture "memory_pressure" memory_pressure || true
  # swap usage
  run_capture "swapfile_list" sysctl vm.swapusage || true
else
  # assume Linux
  run_if_exists free run_capture "free_h" free -h
  run_if_exists vmstat run_capture "vmstat" vmstat -s
  run_if_exists iostat run_capture "iostat_1_5" iostat -x 1 5
  run_if_exists sar run_capture "sar_-u" sar -u 1 5 || true
  run_if_exists "swapon" run_capture "swapon_show" swapon --show || true
fi

# I/O and disk usage heavy hitters
run_capture "du_top_level" sh -c 'du -sh ./* 2>/dev/null | sort -hr | head -n 50' || true
run_capture "du_reports" sh -c 'du -sh reports/* 2>/dev/null | sort -hr | head -n 50' || true

# Open files / sockets
run_if_exists lsof run_capture "lsof_top" lsof -nP -c python | head -n 200 || true
run_if_exists lsof run_capture "lsof_all_top" lsof -nP | head -n 200 || true

# Docker diagnostics (if docker is installed)
if command -v docker >/dev/null 2>&1; then
  run_capture "docker_ps" docker ps -a
  # docker stats without streaming
  run_capture "docker_stats" docker stats --no-stream --format "table {{.Container}}\t{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
  # images and volumes
  run_capture "docker_images" docker images --format "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}"
  run_capture "docker_df" docker system df
else
  echo "docker not installed or not in PATH" > "${OUT_DIR}/SKIPPED_docker.txt"
fi

# If systemd journal is available, capture recent logs (Linux only)
if command -v journalctl >/dev/null 2>&1; then
  run_capture "journalctl_recent" journalctl -n 500 --no-pager || true
fi

# Git status and recent commits (helpful when running from a repo)
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  run_capture "git_status" git status --porcelain --untracked-files=normal
  run_capture "git_log" git -c core.pager= log --oneline --decorate --graph -n 100
fi

# Python-specific diagnostics
#  - list python processes
#  - for each python pid capture: ps -o pid,ppid,pcpu,pmem,args ; open files (lsof -p) ; optional sample via py-spy or sample
PY_PIDS="$(pgrep -f -a python || true)"
echo "python pids: ${PY_PIDS}" > "${OUT_DIR}/python_pids.txt" 2>&1 || true

# Use pgrep to gather numeric PIDs
mapfile -t PY_PIDS_ARRAY < <(pgrep -f python || true)

if [ "${#PY_PIDS_ARRAY[@]}" -eq 0 ]; then
  echo "No python processes found" > "${OUT_DIR}/python_processes_none.txt"
else
  idx=0
  for pid in "${PY_PIDS_ARRAY[@]}"; do
    idx=$((idx + 1))
    # Basic process line
    run_capture "python_${pid}_ps" ps -p "${pid}" -o pid,ppid,%cpu,%mem,etime,cmd
    # lsof for pid if available
    if command -v lsof >/dev/null 2>&1; then
      run_capture "python_${pid}_lsof" lsof -nP -p "${pid}" | head -n 500 || true
    fi

    # Try to capture a Python stack/profile sample
    if command -v py-spy >/dev/null 2>&1; then
      echo "py-spy found, recording top and a short flamegraph for PID ${pid}"
      # top (text) sample for a short duration
      { py-spy top --pid "${pid}" --duration 10 > "${OUT_DIR}/python_${pid}_pyspy_top.txt" 2>&1; } || true
      # flamegraph (svg)
      { py-spy record --pid "${pid}" --duration 10 --output "${OUT_DIR}/python_${pid}_flame.svg" 2> "${OUT_DIR}/python_${pid}_pyspy_record.err"; } || true
      # folded stack (useful for offline flamegraphing)
      { py-spy dump --pid "${pid}" --raw --format speedscope > "${OUT_DIR}/python_${pid}_speedscope.json" 2> "${OUT_DIR}/python_${pid}_pyspy_dump.err"; } || true
    elif command -v sample >/dev/null 2>&1 && [[ "${OS_NAME}" == "darwin" ]]; then
      # macOS fallback - sample is built-in and produces a text report
      echo "macOS sample utility found, capturing sample for PID ${pid}"
      { sample "${pid}" 10 -file "${OUT_DIR}/python_${pid}_sample.txt" 2> "${OUT_DIR}/python_${pid}_sample.err"; } || true
    else
      echo "No py-spy or sample available for PID ${pid}; consider installing py-spy for low-overhead profiling" > "${OUT_DIR}/python_${pid}_no_profiler.txt"
      # As a lower-level fallback, capture Python traceback if proc supports it (Linux only)
      if [ -r "/proc/${pid}/cmdline" ] && command -v gdb >/dev/null 2>&1; then
        echo "Attempting gdb backtrace for PID ${pid} (may require privileges)" > "${OUT_DIR}/python_${pid}_gdb_note.txt"
        { gdb -p "${pid}" -batch -ex "thread apply all bt" > "${OUT_DIR}/python_${pid}_gdb_bt.txt" 2>&1; } || true
      fi
    fi
  done
fi

# Collect recent logs for the repository if present (look for common log dirs)
if [ -d "logs" ]; then
  run_capture "repo_logs_tail" sh -c 'for f in logs/*; do echo "=== $f ==="; tail -n 200 "$f"; done' || true
fi

# Collect environment variables relevant to Python / Docker / Dagster
run_capture "env_python_related" env | egrep -i 'PY|VIRTUAL|VENV|POETRY|PIP|DOCKER|DAGSTER' || true

# Capture installed Python packages (if running within a virtualenv or system python)
if command -v python3 >/dev/null 2>&1; then
  run_capture "python3_package_list" python3 -m pip list --format=columns || true
fi
if command -v python >/dev/null 2>&1; then
  run_capture "python_package_list" python -m pip list --format=columns || true
fi

# Quick network check
run_if_exists ss run_capture "ss_listen" ss -ltnp || run_capture "netstat_listen" netstat -ltnp || true

# Summarize biggest files in the repo and tmp directories
run_capture "largest_files_repo" sh -c 'find . -type f -xdev -size +1M -print0 2>/dev/null | xargs -0 du -h 2>/dev/null | sort -hr | head -n 50' || true
run_capture "tmp_usage" sh -c 'du -sh /tmp/* 2>/dev/null | sort -hr | head -n 50' || true

# Package outputs into a tar.gz for easy transfer
ARCHIVE_NAME="${OUT_DIR}.tar.gz"
tar -czf "${ARCHIVE_NAME}" -C "$(dirname "${OUT_DIR}")" "$(basename "${OUT_DIR}")" || true

echo "Diagnostics collection complete."
echo "Collected files are in: ${OUT_DIR}"
echo "Compressed archive: ${ARCHIVE_NAME}"
echo "End time (UTC): $(date -u)" >> "${OUT_DIR}/collection_meta.txt"
