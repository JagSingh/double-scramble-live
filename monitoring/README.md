# Double Scramble, Live monitoring

Two checks, alerting through Healthchecks.io. One reads the container's log on the production host.
The other checks the YouTube channel from a second, independent machine. After each run the scripts
ping a Healthchecks check: a normal ping when the check passes, `/fail` when it fails. If a ping
arrives late or not at all (host down, cron stopped, home internet down), Healthchecks alerts on
that too.

## Hosts

| Role | What it is | Runs |
|---|---|---|
| **prod-primary** | The machine running the double-scramble-live container | `install-prod-primary.sh` |
| **monitor-secondary** | Any other always-on Linux machine; it must not be prod-primary | `install-monitor-secondary.sh` |

## The checks

| Check | Host | Runs at (Chicago time) | Passes when |
|---|---|---|---|
| `dsl-log` | prod-primary | 12:00, 16:00 | the container log shows your event text (`DSL_PATTERN`) in the last 4 h |
| `dsl-live` | monitor-secondary | 12:00 | the channel's `/live` page contains `"isLiveNow":true` |

**Why both checks are needed:** they catch different failures. `dsl-log` shows the process is
turning aircraft into musical events. `dsl-live` shows YouTube is actually broadcasting. In the
Oct 1 2026 incident, the container kept logging events normally for about 34 h while the YouTube
broadcast had ended. Only `dsl-live` would have caught that.

## What an alert means

| Alert | Likely cause | First thing to look at |
|---|---|---|
| `dsl-log` | No musical events are being produced | Container status, ADS-B input (readsb), the ffmpeg pipeline |
| `dsl-live` (with `dsl-log` passing) | The broadcast ended or isn't bound to the stream | YouTube Studio; whether ffmpeg is pushing to a key that has no live broadcast |
| `dsl-log` **"no ping"** (late) | prod-primary or its cron didn't run | Is the host up, is cron running |
| Both **"no ping"** | Home internet or power is down | Router, power |

## Setup

### 1. Healthchecks.io

Create two checks, both with:

- **Type:** Cron
- **Timezone:** America/Chicago
- **Grace:** 1 hour

| Check | Schedule |
|---|---|
| `dsl-log` | `0 12,16 * * *` |
| `dsl-live` | `0 12 * * *` |

A schedule like `0 12,16 * * *` means minute 0, hours 12 and 16, every day.

Add a notification channel under Integrations. Copy each check's ping URL; the UUID is the part
after `https://hc-ping.com/`.

### 2. Choose `DSL_PATTERN`

Pick literal text that appears only on the log lines for musical events. Then check how often it
appears:

```bash
docker logs --since 4h <container> 2>&1 | grep -cF '<candidate text>'
```

During the day the count should be well above 0.

### 3. prod-primary

```bash
cd monitoring
./install-prod-primary.sh               # first run creates ~/monitoring/double-scramble-live/monitoring.env and stops
nano ~/monitoring/double-scramble-live/monitoring.env  # set DSL_CONTAINER, DSL_PATTERN (keep the quotes), HC_DSL_LOG
./install-prod-primary.sh --test
```

### 4. monitor-secondary

```bash
cd monitoring
./install-monitor-secondary.sh            # installs cron + curl if missing, creates ~/monitoring/double-scramble-live/monitoring.env, stops
nano ~/monitoring/double-scramble-live/monitoring.env    # set HC_DSL_LIVE
./install-monitor-secondary.sh --test
```

### Installed files

Each project gets one visible folder on each host, outside the git checkout:

```
~/monitoring/double-scramble-live/
  monitor-primary.sh     (prod-primary) or monitor-secondary.sh (monitor-secondary)
  monitoring.env         UUIDs and settings (mode 600; not in git)
  monitoring.log         one line per check per run
```

The cron line is tagged `# double-scramble-monitor-…`. Cron runs the script from this folder, so you can
delete, re-clone or switch branches in the repo without affecting monitoring. Other projects use
their own folders under `~/monitoring/`, so they don't conflict.

To install somewhere else, set `MON_DIR` when running the installer, e.g.
`MON_DIR=~/ops/double-scramble-live ./install-prod-primary.sh`. Use the same `MON_DIR` each time you rerun it.

### How scheduling works

Cron runs the check script every hour on the hour. The script checks the time in Chicago and exits
unless the hour is a scheduled one. This means the machine's own timezone setting doesn't matter.

## Testing

### Test 1: everything passes and the pings arrive

```bash
# prod-primary
./install-prod-primary.sh --test
#   ... dsl-log ok: N x '<pattern>' in last 4h

# monitor-secondary
./install-monitor-secondary.sh --test
#   ... dsl-live ok: live
```

**Pass if:** both checks show green in Healthchecks.

### Test 2: alerts actually reach you

This sends a real alert.

```bash
# prod-primary: report the check as failed
FORCE=1 FORCE_FAIL=1 ~/monitoring/double-scramble-live/monitor-primary.sh
```

**Pass if:** you receive the `dsl-log` alert within about a minute.

Then restore with `FORCE=1 ~/monitoring/double-scramble-live/monitor-primary.sh`. You should receive a recovery
notice.

### Test 3: the time gate

```bash
~/monitoring/double-scramble-live/monitor-primary.sh; echo "exit=$?"   # outside 12:00/16:00: no output, exit=0, no ping
```

### Test 4: cron is firing

After the next scheduled run:

```bash
tail ~/monitoring/double-scramble-live/monitoring.log
```

## Running it

| Task | Command |
|---|---|
| Recent results | `tail -20 ~/monitoring/double-scramble-live/monitoring.log` |
| Run checks now | `FORCE=1 ~/monitoring/double-scramble-live/monitor-primary.sh` (or `monitor-secondary.sh`) |
| Change UUID, container or pattern | Edit `~/monitoring/double-scramble-live/monitoring.env`. The next run uses it. |
| Check the broadcast more often | On monitor-secondary set `RUN_HOURS="0 4 8 12 16 20"` in the env file, then change the `dsl-live` schedule to `0 0,4,8,12,16,20 * * *` |

If one machine is both prod-primary and monitor-secondary, both installers share
`~/monitoring/double-scramble-live/monitoring.env`. The second installer will report which variable is missing;
add it to the file and rerun.

## Known limits

- **`dsl-live` runs once a day by default,** so a broadcast that has ended can go up to about 24
  hours before you're alerted. The "check more often" row above shortens that.
- **`dsl-live` depends on YouTube's page markup.** If YouTube renames `isLiveNow`, the check will
  report "not live" even though the stream is up, so you'll get an alert rather than miss an
  outage.
- **`dsl-log` depends on log text.** If the event log line changes, update `DSL_PATTERN`.
- **Logs are read from both stdout and stderr** (`2>&1`). Python `logging` writes to stderr, so
  without that the count would be 0.

## Test results before delivery

The scripts were run in a sandbox using stand-in versions of `docker`, `curl` and `crontab`:

- **Bash syntax:** both installers pass.
- **First run:** creates `~/monitoring/double-scramble-live/monitoring.env` with mode 600 and stops. An empty `DSL_PATTERN`, an empty
  UUID or an unknown container each stops the install with a clear error.
- **Passing run:** `dsl-log` matched the event text and `dsl-live` found `isLiveNow`. Both success
  pings were sent.
- **Failure runs:** each of these sent the matching `/fail` ping:
  - a missing container
  - a YouTube page without `isLiveNow`
- **Time gate:** outside the run hours, no pings are sent.
- **Alongside plane_spotter's monitoring on the same host:** the env files, scripts, logs and cron
  lines are all separate. An unrelated existing cron job survives every install.
- **Install folder:** cron runs the script from another working directory and it still finds
  `monitoring.env` next to itself. `MON_DIR` moves the folder.

- **Alert test switch:** `FORCE_FAIL=1` sends `/fail` for every check on both hosts, even when the
  real checks would pass. The env file can't override it.
- **Not tested here:** the real Docker, YouTube and Healthchecks. Tests 1-2 above cover that on the
  actual machines.
