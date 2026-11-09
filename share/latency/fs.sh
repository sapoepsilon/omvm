#!/bin/bash
# fs.sh: make the Reims vGPU window fullscreen (local mode's normal state) and print its geometry
export HYPRLAND_INSTANCE_SIGNATURE=$(ls -t /run/user/1000/hypr | head -1)
hyprctl eval 'for _, w in ipairs(hl.get_windows()) do if w.class == "reims-vgpu" and (w.fullscreen or 0) ~= 2 then hl.dispatch(hl.dsp.window.fullscreen({ mode = "fullscreen", action = "set", window = w })) end end' >/dev/null
sleep 0.5
hyprctl -j clients | python3 -c '
import json,sys
for c in json.load(sys.stdin):
    if c["class"] == "reims-vgpu": print("reims window", c["at"], c["size"], "fullscreen", c["fullscreen"])'
