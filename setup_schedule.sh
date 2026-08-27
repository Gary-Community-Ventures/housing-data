#!/bin/bash
# Install a daily 06:10 collection run via launchd (macOS).
set -e
PLIST=~/Library/LaunchAgents/org.garycommunity.housing-daily.plist
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>org.garycommunity.housing-daily</string>
  <key>ProgramArguments</key><array>
    <string>$(pwd)/.venv/bin/python</string>
    <string>$(pwd)/run_daily.py</string>
  </array>
  <key>WorkingDirectory</key><string>$(pwd)</string>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>6</integer><key>Minute</key><integer>10</integer>
  </dict>
  <key>StandardOutPath</key><string>$(pwd)/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>$(pwd)/logs/launchd.err</string>
</dict></plist>
PLISTEOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "installed: daily run at 06:10 (lockfile prevents overlap). Remove with:"
echo "  launchctl unload $PLIST && rm $PLIST"
