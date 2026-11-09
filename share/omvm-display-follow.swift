// SPDX-License-Identifier: GPL-2.0-or-later
// omvm guest agent: run each display at macOS's default mode whenever the host offers a new one.
//
// QEMU's apple-gfx (omvm patch qemu/0003) offers a headless display the size a VNC viewer's
// window asks for, as the display's only mode. macOS switches to it when the mode it runs is no
// longer offered (a smaller window), but when the viewer grows it keeps the mode it runs (still
// one of the scaled modes it derives from the new one) or goes back to the mode saved for the
// display in com.apple.windowserver.displays. This agent, a LaunchAgent in the user's session,
// sets the new size's default mode each time it changes: the one macOS marks default (Displays'
// "Default", kDisplayModeDefaultFlag), Retina where the host reports a HiDPI density (local mode's
// 3024x1964@254 runs 1512x982 points), else the native mode (the largest 1x one).
//
// The last size it acted on is kept in ~/Library/omvm/display-follow.state, so a guest that
// boots to the same size keeps the scaling picked in System Settings; a new size (or no state)
// gets the default again.
//
// Build in the guest: swiftc -O omvm-display-follow.swift -o ~/Library/omvm/omvm-display-follow
import CoreGraphics
import Foundation

var pending = false
let stateFile = NSString(string: "~/Library/omvm/display-follow.state").expandingTildeInPath

/// Display id -> "WxH" of the native mode last acted on, across restarts of the agent.
func loadState() -> [String: String] {
    (NSDictionary(contentsOfFile: stateFile) as? [String: String]) ?? [:]
}
func saveState(_ s: [String: String]) {
    (s as NSDictionary).write(toFile: stateFile, atomically: true)
}
var lastNative = loadState()

/// The mode macOS marks default for the display (kDisplayModeDefaultFlag), else `native`.
func defaultMode(_ d: CGDirectDisplayID, _ native: CGDisplayMode) -> CGDisplayMode {
    let kDisplayModeDefaultFlag: UInt32 = 0x0000_0004
    let opts = [kCGDisplayShowDuplicateLowResolutionModes: true] as CFDictionary
    let modes = (CGDisplayCopyAllDisplayModes(d, opts) as? [CGDisplayMode]) ?? []
    return modes.first { $0.ioFlags & kDisplayModeDefaultFlag != 0 && $0.isUsableForDesktopGUI() } ?? native
}

func nativeMode(_ d: CGDirectDisplayID) -> CGDisplayMode? {
    let modes = (CGDisplayCopyAllDisplayModes(d, nil) as? [CGDisplayMode]) ?? []
    return modes.filter { $0.pixelWidth == $0.width && $0.isUsableForDesktopGUI() }
        .max { $0.width * $0.height < $1.width * $1.height }
}

func follow() {
    pending = false
    var count: UInt32 = 0
    var ids = [CGDirectDisplayID](repeating: 0, count: 16)
    guard CGGetOnlineDisplayList(16, &ids, &count) == .success else { return }
    for d in ids.prefix(Int(count)) {
        guard let native = nativeMode(d) else { continue }
        let size = "\(native.width)x\(native.height)", key = String(d)
        // Act only when the offered mode changed, so a mode the user picks in System
        // Settings stays until the viewer is resized (or the host offers another size).
        if lastNative[key] == size { continue }
        lastNative[key] = size
        saveState(lastNative)
        let want = defaultMode(d, native)
        guard let cur = CGDisplayCopyDisplayMode(d),
              cur.width != want.width || cur.height != want.height ||
              cur.pixelWidth != want.pixelWidth else { continue }
        var cfg: CGDisplayConfigRef?
        guard CGBeginDisplayConfiguration(&cfg) == .success else { continue }
        CGConfigureDisplayWithDisplayMode(cfg, d, want, nil)
        let err = CGCompleteDisplayConfiguration(cfg, .permanently)
        print("display \(d): \(cur.width)x\(cur.height)/\(cur.pixelWidth)px -> \(want.width)x\(want.height)/\(want.pixelWidth)px (default): \(err.rawValue)")
        fflush(stdout)
    }
}

CGDisplayRegisterReconfigurationCallback({ _, flags, _ in
    if flags.contains(.beginConfigurationFlag) || pending { return }
    pending = true
    // Let the burst of reconfigurations, and WindowServer's own choice, settle first.
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { follow() }
}, nil)
setvbuf(stdout, nil, _IOLBF, 0)
follow()
CFRunLoopRun()  // the reconfiguration callback comes through the main run loop
