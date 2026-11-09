-- macOS VM keyboard passthrough and switching (omvm). Append to ~/.config/hypr/bindings.lua.
--
-- Switching (works in both modes, even while the VM has captured the keyboard:
-- dont_inhibit gets past the shortcuts inhibitor reims-vgpu's window holds while
-- captured, submap_universal past the VNC viewer's "macos-vm" submap):
--   Ctrl+Alt+M       macOS <-> Omarchy: from the VM back to the window you came
--                    from; from anywhere else to the VM (its local window, its
--                    VNC viewer, or `omvm show`, which opens one)
--   Ctrl+Alt+1..5    leave the VM for Omarchy workspace 1..5
-- Leaving the VM's window releases its capture (it loses the keyboard).
--
-- Passthrough (remote mode): while a VNC viewer window has focus, every key
-- (Super = Cmd included) goes to the macOS guest: Hyprland switches to the empty
-- "macos-vm" submap. Ctrl+Alt+Escape gives the keys back while the viewer stays
-- focused; clicking or focusing any other window gives them back too.
local function is_vm_viewer(w)
  local c = (w and w.class or ""):lower()
  return c:find("vncviewer", 1, true) ~= nil
end
local function is_vm(w)
  return is_vm_viewer(w) or (w and (w.class or ""):lower() == "reims-vgpu") or false
end
local function vm_window()
  local viewer = nil
  for _, w in ipairs(hl.get_windows() or {}) do
    if (w.class or ""):lower() == "reims-vgpu" then return w end
    if is_vm_viewer(w) and not viewer then viewer = w end
  end
  return viewer
end
-- The most recently focused window that is not the VM (focus history: 0 = now).
local function vm_last_host()
  local best = nil
  for _, w in ipairs(hl.get_windows() or {}) do
    local h = w.focus_history_id or -1
    if h >= 0 and not is_vm(w) and (not best or h < best.focus_history_id) then best = w end
  end
  return best
end
local function vm_leave(ws)
  hl.dispatch(hl.dsp.submap("reset"))
  if ws then
    hl.dispatch(hl.dsp.focus({ workspace = ws }))
    return
  end
  local back = vm_last_host()
  if back then
    hl.dispatch(hl.dsp.focus({ window = "address:" .. back.address }))
  else
    hl.dispatch(hl.dsp.focus({ workspace = "previous" }))
  end
end
hl.bind("CTRL + ALT + M", function()
  if is_vm(hl.get_active_window()) then
    vm_leave()
  else
    local w = vm_window()
    if w then
      hl.dispatch(hl.dsp.focus({ window = "address:" .. w.address }))
    else
      hl.exec_cmd("omvm show")
    end
  end
end, { dont_inhibit = true, submap_universal = true, description = "macOS VM <-> Omarchy" })
for i = 1, 5 do
  hl.bind("CTRL + ALT + " .. i, function() vm_leave(i) end,
    { dont_inhibit = true, submap_universal = true, description = "Leave the macOS VM for workspace " .. i })
end
hl.define_submap("macos-vm", function()
  hl.bind("CTRL + ALT + ESCAPE", hl.dsp.submap("reset"))
end)
hl.on("window.active", function(w)
  local inside = hl.get_current_submap() == "macos-vm"
  if is_vm_viewer(w) and not inside then
    hl.dispatch(hl.dsp.submap("macos-vm"))
  elseif not is_vm_viewer(w) and inside then
    hl.dispatch(hl.dsp.submap("reset"))
  end
end)
