// omvm-hidpi [W H HIDPI]  -- run inside a macOS guest (by stream-host.sh over ssh).
// Switches the main display to the mode whose backing store is W x H pixels:
// HIDPI=1 -> the Retina mode drawing W/2 x H/2 points, HIDPI=0 -> 1:1.
// W=0 H=0 means "the current pixel size" (used to drop back to 1:1).
// No arguments: print the current mode, change nothing.
// Build in the guest: swiftc -O omvm-hidpi.swift -o /usr/local/bin/omvm-hidpi
import CoreGraphics
import Foundation

let a = CommandLine.arguments
let d = CGMainDisplayID()
guard let cur = CGDisplayCopyDisplayMode(d) else { print("no display mode"); exit(1) }
func fmt(_ m: CGDisplayMode) -> String { "\(m.width)x\(m.height)pt/\(m.pixelWidth)x\(m.pixelHeight)px" }
if a.count == 1 { print(fmt(cur)); exit(0) }   // no arguments: just print the current mode
guard a.count >= 4, var w = Int(a[1]), var h = Int(a[2]), let want = Int(a[3]) else {
    print("usage: omvm-hidpi [W H 0|1]"); exit(2)
}
if w == 0 || h == 0 { w = cur.pixelWidth; h = cur.pixelHeight }
let (lw, lh) = want == 1 ? (w / 2, h / 2) : (w, h)
let opts = [kCGDisplayShowDuplicateLowResolutionModes: true] as CFDictionary
let modes = (CGDisplayCopyAllDisplayModes(d, opts) as? [CGDisplayMode]) ?? []
if cur.width == lw && cur.height == lh && cur.pixelWidth == w && cur.pixelHeight == h {
    print("already \(fmt(cur))"); exit(0)
}
guard let m = modes.first(where: { $0.pixelWidth == w && $0.pixelHeight == h && $0.width == lw && $0.height == lh }) else {
    print("no mode \(lw)x\(lh)pt/\(w)x\(h)px (current \(fmt(cur)))"); exit(1)
}
var cfg: CGDisplayConfigRef?
CGBeginDisplayConfiguration(&cfg)
CGConfigureDisplayWithDisplayMode(cfg, d, m, nil)
let err = CGCompleteDisplayConfiguration(cfg, .permanently)
print(err == .success ? "set \(fmt(m))" : "failed \(err.rawValue)")
exit(err == .success ? 0 : 1)
