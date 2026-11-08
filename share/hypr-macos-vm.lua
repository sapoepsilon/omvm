-- macOS VM keyboard passthrough (omvm). Append to ~/.config/hypr/bindings.lua.
-- While a VNC viewer window has focus, every key (Super = Cmd included) goes
-- to the macOS guest: Hyprland switches to the empty "macos-vm" submap.
-- Ctrl+Alt+Escape gives the keys back while the viewer stays focused;
-- clicking or focusing any other window gives them back too.
local function is_vm_viewer(w)
  local c = (w and w.class or ""):lower()
  return c:find("vncviewer", 1, true) ~= nil
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
