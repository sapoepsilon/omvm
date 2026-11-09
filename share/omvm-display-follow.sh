#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Runs inside the guest (omvm gui pipes it over SSH): builds and loads the display-follow
# LaunchAgent (omvm-display-follow.swift, copied to ~/Library/omvm first), which puts the
# desktop at the size the host offers, in macOS's default scaling. Idempotent.
set -euo pipefail
dir="$HOME/Library/omvm" label=org.omvm.display-follow
src="$dir/omvm-display-follow.swift" bin="$dir/omvm-display-follow"
plist="$HOME/Library/LaunchAgents/$label.plist"
command -v swiftc >/dev/null || { echo "no swiftc (Command Line Tools): display-follow off"; exit 0; }
mkdir -p "$dir" "$HOME/Library/LaunchAgents"
rebuilt=0
if [ ! -x "$bin" ] || [ "$src" -nt "$bin" ]; then
    swiftc -O "$src" -o "$bin.new"
    # Sign it under its own name: the linker's ad-hoc signature says "omvm-display-follow.new",
    # and launchd's first spawn of the rebuilt agent failed (OS_REASON_CODESIGNING) on 27.2.
    codesign -f -s - -i org.omvm.display-follow "$bin.new" 2>/dev/null || true
    mv "$bin.new" "$bin"
    rebuilt=1
fi
cat > "$plist.new" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>$label</string>
<key>ProgramArguments</key><array><string>$bin</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>LimitLoadToSessionType</key><string>Aqua</string>
<key>StandardOutPath</key><string>/tmp/omvm-display-follow.log</string>
<key>StandardErrorPath</key><string>/tmp/omvm-display-follow.log</string>
</dict></plist>
EOF
if cmp -s "$plist.new" "$plist"; then rm "$plist.new"; else mv "$plist.new" "$plist"; fi
# Logged in already: load (or restart) it now; otherwise launchd loads it at login.
uid="$(id -u)"
if launchctl print "gui/$uid" >/dev/null 2>&1; then
    if launchctl print "gui/$uid/$label" >/dev/null 2>&1; then
        [ "$rebuilt" = 0 ] || launchctl kickstart -k "gui/$uid/$label"
    else
        launchctl bootstrap "gui/$uid" "$plist" 2>/dev/null || true
    fi
fi
echo "display-follow ready"
