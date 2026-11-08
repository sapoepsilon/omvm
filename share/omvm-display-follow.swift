// SPDX-License-Identifier: GPL-2.0-or-later
// omvm guest agent: run each display at its native mode whenever the host offers a new one.
//
// QEMU's apple-gfx (omvm patch qemu/0003) offers a headless display the size a VNC viewer's
// window asks for, as the display's only mode. macOS switches to it when the mode it runs is no
// longer offered (a smaller window), but when the viewer grows it keeps the mode it runs (still
// one of the scaled modes it derives from the new one) or goes back to the mode saved for the
// display in com.apple.windowserver.displays. This agent, a LaunchAgent in the user's session,
// sets the new native mode (the largest 1x mode) each time it changes.
//
// Build in the guest: swiftc -O omvm-display-follow.swift -o ~/Library/omvm/omvm-display-follow
import CoreGraphics
import Foundation

var lastNative: [CGDirectDisplayID: (Int, Int)] = [:]
var pending = false

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
        let size = (native.width, native.height)
        // Act only when the offered mode changed, so a mode the user picks in System
        // Settings stays until the viewer is resized.
        if let last = lastNative[d], last == size { continue }
        lastNative[d] = size
        guard let cur = CGDisplayCopyDisplayMode(d),
              cur.width != native.width || cur.height != native.height ||
              cur.pixelWidth != native.pixelWidth else { continue }
        var cfg: CGDisplayConfigRef?
        guard CGBeginDisplayConfiguration(&cfg) == .success else { continue }
        CGConfigureDisplayWithDisplayMode(cfg, d, native, nil)
        let err = CGCompleteDisplayConfiguration(cfg, .permanently)
        print("display \(d): \(cur.width)x\(cur.height) -> \(native.width)x\(native.height): \(err.rawValue)")
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
