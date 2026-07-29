#!/usr/bin/env bash
# Install a launchd job that rebuilds the dashboard every morning.
#
# Why launchd and not cron: this is a laptop. It sleeps. cron simply skips a
# job whose fire time passed while the machine was asleep, so a 7am cron on a
# closed MacBook never runs. launchd's StartCalendarInterval catches up on the
# next wake, which is the behavior you actually want.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOUR="${1:-7}"
MIN="${2:-15}"
LABEL="com.lucas.sportsdashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$DIR/scripts/run.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MIN</integer>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$DIR/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.err.log</string>
  <key>WorkingDirectory</key><string>$DIR</string>
</dict>
</plist>
PLIST_EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed $LABEL — runs daily at $(printf '%02d:%02d' "$HOUR" "$MIN") local time."
echo "  run now:    launchctl start $LABEL"
echo "  check:      launchctl list | grep sportsdashboard"
echo "  uninstall:  launchctl unload $PLIST && rm $PLIST"
echo "  logs:       tail -f $DIR/logs/run.log"
