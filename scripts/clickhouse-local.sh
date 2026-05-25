#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${CLICKSPOT_CLICKHOUSE_DIR:-$ROOT/.clickhouse}"
BIN_DIR="$RUNTIME_DIR/bin"
CONFIG_DIR="$RUNTIME_DIR/config"
DATA_DIR="$RUNTIME_DIR/data"
LOG_DIR="$RUNTIME_DIR/logs"
TMP_DIR="$RUNTIME_DIR/tmp"
PID_FILE="$RUNTIME_DIR/clickhouse.pid"
VERSION="${CLICKHOUSE_VERSION:-26.2.5.45}"
HTTP_PORT="${CLICKHOUSE_PORT:-8124}"
TCP_PORT="${CLICKHOUSE_NATIVE_PORT:-9001}"
CH_USER="${CLICKHOUSE_USER:-hs2ch}"
CH_PASSWORD="${CLICKHOUSE_PASSWORD:-hs2ch}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[clickhouse]${NC} $1"; }
warn() { echo -e "${YELLOW}[clickhouse]${NC} $1"; }
err()  { echo -e "${RED}[clickhouse]${NC} $1" >&2; }

binary_path() {
  if [ -n "${CLICKHOUSE_BIN:-}" ]; then
    printf '%s\n' "$CLICKHOUSE_BIN"
  elif [ -x "$BIN_DIR/clickhouse" ]; then
    printf '%s\n' "$BIN_DIR/clickhouse"
  elif command -v clickhouse >/dev/null 2>&1; then
    command -v clickhouse
  else
    printf '%s\n' "$BIN_DIR/clickhouse"
  fi
}

ping_clickhouse() {
  curl -sf "http://127.0.0.1:${HTTP_PORT}/ping" >/dev/null 2>&1
}

write_config() {
  mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" "$TMP_DIR" \
    "$RUNTIME_DIR/user_files" "$RUNTIME_DIR/format_schemas" "$RUNTIME_DIR/access"

  cat > "$CONFIG_DIR/config.xml" <<XML
<clickhouse>
    <logger>
        <level>information</level>
        <log>$LOG_DIR/clickhouse.log</log>
        <errorlog>$LOG_DIR/clickhouse.err.log</errorlog>
        <size>100M</size>
        <count>3</count>
    </logger>

    <path>$DATA_DIR/</path>
    <tmp_path>$TMP_DIR/</tmp_path>
    <user_files_path>$RUNTIME_DIR/user_files/</user_files_path>
    <format_schema_path>$RUNTIME_DIR/format_schemas/</format_schema_path>
    <access_control_path>$RUNTIME_DIR/access/</access_control_path>

    <listen_host>127.0.0.1</listen_host>
    <http_port>$HTTP_PORT</http_port>
    <tcp_port>$TCP_PORT</tcp_port>
    <interserver_http_port>9010</interserver_http_port>

    <users_config>$CONFIG_DIR/users.xml</users_config>
    <default_profile>default</default_profile>
    <default_database>default</default_database>

    <mark_cache_size>536870912</mark_cache_size>
    <uncompressed_cache_size>268435456</uncompressed_cache_size>
    <merge_tree>
        <index_granularity>4096</index_granularity>
    </merge_tree>
</clickhouse>
XML

  cat > "$CONFIG_DIR/users.xml" <<XML
<clickhouse>
    <profiles>
        <default>
            <max_memory_usage>2000000000</max_memory_usage>
            <max_bytes_before_external_group_by>500000000</max_bytes_before_external_group_by>
            <max_bytes_before_external_sort>500000000</max_bytes_before_external_sort>
            <max_result_rows>100000</max_result_rows>
            <result_overflow_mode>throw</result_overflow_mode>
            <max_partitions_per_insert_block>500</max_partitions_per_insert_block>
        </default>
    </profiles>

    <users>
        <$CH_USER>
            <password>$CH_PASSWORD</password>
            <profile>default</profile>
            <quota>default</quota>
            <access_management>1</access_management>
            <networks>
                <ip>127.0.0.1</ip>
                <ip>::1</ip>
            </networks>
        </$CH_USER>
    </users>

    <quotas>
        <default>
            <interval>
                <duration>3600</duration>
                <queries>0</queries>
                <errors>0</errors>
                <result_rows>0</result_rows>
                <read_rows>0</read_rows>
                <execution_time>0</execution_time>
            </interval>
        </default>
    </quotas>
</clickhouse>
XML
}

install_binary() {
  local bin
  bin="$(binary_path)"
  if [ -x "$bin" ]; then
    log "Using ClickHouse binary: $bin"
    return 0
  fi

  if [ "$(uname -s)" != "Linux" ]; then
    err "Automatic ClickHouse download is only supported on Linux."
    err "On macOS/Windows, run against the container instead: set"
    err "CLICKSPOT_CLICKHOUSE_MODE=docker in .env (already the default there)."
    err "Or install ClickHouse yourself and set CLICKHOUSE_BIN=/path/to/clickhouse."
    return 1
  fi

  local arch package_arch url archive tmpdir extracted
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) package_arch="amd64" ;;
    aarch64|arm64) package_arch="arm64" ;;
    *) err "Unsupported architecture: $arch"; return 1 ;;
  esac

  mkdir -p "$BIN_DIR"
  url="${CLICKHOUSE_DOWNLOAD_URL:-https://packages.clickhouse.com/tgz/stable/clickhouse-common-static-${VERSION}-${package_arch}.tgz}"
  archive="$RUNTIME_DIR/clickhouse-${VERSION}-${package_arch}.tgz"
  tmpdir="$RUNTIME_DIR/download"

  log "Downloading ClickHouse $VERSION ($package_arch)..."
  curl -fL "$url" -o "$archive"
  rm -rf "$tmpdir"
  mkdir -p "$tmpdir"
  tar -xzf "$archive" -C "$tmpdir"
  extracted="$(find "$tmpdir" -type f -name clickhouse | head -n 1)"
  if [ -z "$extracted" ]; then
    err "Downloaded archive did not contain a clickhouse binary."
    return 1
  fi
  cp "$extracted" "$BIN_DIR/clickhouse"
  chmod +x "$BIN_DIR/clickhouse"
  rm -rf "$tmpdir"
  log "Installed ClickHouse to $BIN_DIR/clickhouse"
}

wait_ready() {
  for _ in $(seq 1 60); do
    if ping_clickhouse; then
      log "Ready on http://127.0.0.1:${HTTP_PORT}"
      return 0
    fi
    sleep 1
  done
  err "ClickHouse did not become ready. Last log lines:"
  tail -n 40 "$LOG_DIR/stderr.log" 2>/dev/null || true
  tail -n 40 "$LOG_DIR/clickhouse.err.log" 2>/dev/null || true
  return 1
}

start() {
  write_config
  install_binary

  if ping_clickhouse; then
    log "Already reachable on http://127.0.0.1:${HTTP_PORT}"
    return 0
  fi
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "Process already running as PID $(cat "$PID_FILE"); waiting for readiness"
    wait_ready
    return 0
  fi

  local bin
  bin="$(binary_path)"
  log "Starting local ClickHouse..."
  nohup "$bin" server --config-file="$CONFIG_DIR/config.xml" > "$LOG_DIR/stdout.log" 2> "$LOG_DIR/stderr.log" &
  echo $! > "$PID_FILE"
  wait_ready
}

stop() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "Stopping PID $(cat "$PID_FILE")"
    kill "$(cat "$PID_FILE")"
    for _ in $(seq 1 20); do
      if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        rm -f "$PID_FILE"
        return 0
      fi
      sleep 1
    done
    warn "Process did not exit after SIGTERM; sending SIGKILL"
    kill -9 "$(cat "$PID_FILE")" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
}

status() {
  if ping_clickhouse; then
    log "Reachable on http://127.0.0.1:${HTTP_PORT}"
  elif [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    warn "PID $(cat "$PID_FILE") is running but /ping is not ready"
  else
    warn "Stopped"
    return 1
  fi
}

case "${1:-start}" in
  ensure) write_config; install_binary ;;
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  wait) wait_ready ;;
  path) binary_path ;;
  *)
    cat <<'USAGE'
Usage: scripts/clickhouse-local.sh [ensure|start|stop|restart|status|wait|path]

Environment:
  CLICKHOUSE_VERSION       Version to download when no binary exists (default: 26.2.5.45)
  CLICKHOUSE_BIN           Existing clickhouse binary to use
  CLICKHOUSE_PORT          HTTP port (default: 8124)
  CLICKHOUSE_NATIVE_PORT   Native TCP port (default: 9001)
  CLICKSPOT_CLICKHOUSE_DIR Runtime directory (default: .clickhouse)
USAGE
    exit 2
    ;;
esac
