#!/usr/bin/env bash
# install-monitor-secondary.sh - double-scramble-live YouTube-live check on an independent always-on host.
#
#   ./install-monitor-secondary.sh              install / update (idempotent)
#   ./install-monitor-secondary.sh --test       install, then run the check now (sends a real ping)
#
# Installs into ~/monitoring/double-scramble-live/ (override with MON_DIR=...):
#   monitor-secondary.sh   the check script
#   monitoring.env         Healthchecks UUIDs + settings, mode 600 (template on first run)
#   monitoring.log         one line per check per run
#   (also installs cron + curl via apt if missing; minimal Debian images such as Crostini lack cron)
#   crontab entry          hourly; the script acts only at 12:00 America/Chicago
set -euo pipefail

MON_DIR="${MON_DIR:-$HOME/monitoring/double-scramble-live}"
ENV_FILE="$MON_DIR/monitoring.env"
BIN="$MON_DIR/monitor-secondary.sh"
LOG="$MON_DIR/monitoring.log"
MARK="# double-scramble-monitor-secondary (managed by install-monitor-secondary.sh)"

crontab_without_mark() { { crontab -l 2>/dev/null || true; } | { grep -vF "$MARK" || true; }; }

# ---- prerequisites
missing=()
command -v crontab >/dev/null || missing+=(cron)
command -v curl    >/dev/null || missing+=(curl)
if [ ${#missing[@]} -gt 0 ]; then
  echo "Installing: ${missing[*]}"
  sudo apt-get update -qq && sudo apt-get install -y -qq "${missing[@]}"
fi
sudo systemctl enable --now cron >/dev/null 2>&1 || sudo service cron start
systemctl is-active --quiet cron 2>/dev/null || pgrep -x cron >/dev/null || { echo "ERROR: cron is not running" >&2; exit 1; }

# ---- install folder
mkdir -p "$MON_DIR"

# ---- config
if [ ! -f "$ENV_FILE" ]; then
  umask 077
  cat > "$ENV_FILE" <<'EOF'
# double-scramble-live monitoring config (monitor-secondary). Sourced by monitor-secondary.sh in this folder.
# Healthchecks.io ping UUID: check -> "Ping URL" -> the part after https://hc-ping.com/
HC_DSL_LIVE=
# Optional overrides
#RUN_HOURS="12"
#YT_CHANNEL_ID=UCC0xRipId7fiH_HiN-xUzQA
EOF
  echo "Created $ENV_FILE (mode 600). Fill in the UUID, then rerun: $0 ${1:-}"
  exit 1
fi
# shellcheck source=/dev/null
. "$ENV_FILE"
[ -n "${HC_DSL_LIVE:-}" ] || { echo "ERROR: HC_DSL_LIVE is empty in $ENV_FILE" >&2; exit 1; }

# ---- check script
cat > "$BIN" <<'EOF'
#!/usr/bin/env bash
# monitor-secondary.sh - installed by install-monitor-secondary.sh. Rerun the installer to update.
# Runs hourly from cron; acts only at RUN_HOURS (America/Chicago). FORCE=1 runs now; FORCE_FAIL=1 reports failure (alert test).
set -u
export TZ=America/Chicago PATH="$PATH:/usr/local/bin:/usr/bin:/bin"
# shellcheck source=/dev/null
. "${ENV_FILE:-$(cd "$(dirname "$0")" && pwd)/monitoring.env}"
RUN_HOURS="${RUN_HOURS:-12}"
CHANNEL="${YT_CHANNEL_ID:-UCC0xRipId7fiH_HiN-xUzQA}"
if [ "${FORCE:-0}" != 1 ] && [[ " $RUN_HOURS " != *" $(date +%H) "* ]]; then exit 0; fi

# YouTube broadcast is live
if [ "${FORCE_FAIL:-0}" != 1 ] && curl -fsS -m 30 -A 'Mozilla/5.0' -H 'Accept-Language: en-US' \
     "https://www.youtube.com/channel/$CHANNEL/live" | grep -E '"isLive(Now)?":true' >/dev/null; then
  status=ok; msg="live"; url="https://hc-ping.com/$HC_DSL_LIVE"
else
  status=FAIL; msg="channel not live (isLive not found)"; [ "${FORCE_FAIL:-0}" = 1 ] && msg="forced test failure (FORCE_FAIL=1)"; url="https://hc-ping.com/$HC_DSL_LIVE/fail"
fi
echo "$(date '+%F %T %Z') dsl-live $status: $msg"
curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$msg" "$url" || echo "  ping failed: $url"
EOF
chmod 755 "$BIN"
echo "Installed $BIN"

# ---- cron (hourly at :00; the script gates on Chicago hour, so a UTC system clock doesn't matter)
{ crontab_without_mark; echo "0 * * * * $BIN >> $LOG 2>&1 $MARK"; } | crontab -
echo "Installed cron entry:"; crontab -l | grep -F "$MARK"

if [ "${1:-}" = "--test" ]; then
  echo "--- test run (real ping) ---"
  FORCE=1 "$BIN"
fi
