// latprobe: full-screen window that turns white when the pointer is on the right half and
// black on the left, the moment the mouse-moved event arrives; prints "m <wall> <x> <side>"
// per event, and answers "p" on stdin with "t <wall>" (for host/guest clock offset).
import AppKit
import QuartzCore
setvbuf(stdout, nil, _IOLBF, 0)
func now() -> Double { Date().timeIntervalSince1970 }
final class V: NSView {
    var side = -1
    override init(frame: NSRect) { super.init(frame: frame); wantsLayer = true; layer!.backgroundColor = NSColor.black.cgColor }
    required init?(coder: NSCoder) { fatalError() }
    override func mouseMoved(with e: NSEvent) {
        let t = now()
        let x = e.locationInWindow.x
        let s = x > bounds.midX ? 1 : 0
        if s != side {
            side = s
            CATransaction.begin(); CATransaction.setDisableActions(true)
            layer!.backgroundColor = (s == 1 ? NSColor.white : NSColor.black).cgColor
            CATransaction.commit()
        }
        print(String(format: "m %.6f %.1f %d", t, x, s))
    }
    override func mouseDragged(with e: NSEvent) { mouseMoved(with: e) }
}
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let scr = NSScreen.main!
let win = NSWindow(contentRect: scr.frame, styleMask: [.borderless], backing: .buffered, defer: false)
win.level = .screenSaver
win.acceptsMouseMovedEvents = true
let v = V(frame: scr.frame)
win.contentView = v
win.makeKeyAndOrderFront(nil)
win.makeFirstResponder(v)
app.activate(ignoringOtherApps: true)
Thread.detachNewThread {
    while let l = readLine() {
        if l == "p" { print(String(format: "t %.6f", now())) }
        if l == "q" { exit(0) }
    }
    exit(0)
}
print("ready \(scr.frame.size)")
app.run()
