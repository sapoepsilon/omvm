// SPDX-License-Identifier: GPL-2.0-or-later
// winlist: on-screen window geometry of the logged-in macOS session, as JSON.
// Built and run in the guest by `omac windows`. Needs no Screen Recording grant
// for ids, owners and bounds; window titles stay empty without it.
//
//   winlist [--apps]                      one JSON document
//   winlist --watch [--hz N] [--apps]     one JSON line per change (default 30 Hz poll)
//
// --apps: "windows" = normal app windows (layer 0, non-zero size, not Dock/Window
// Server/menu-bar items); "overlays" = higher-layer windows (menus, popovers,
// panels) owned by a pid that has an app window, plus UserNotificationCenter
// permission prompts. Menus are reported with a transparent shadow margin
// (~75 pt each side on macOS 27); app windows are reported without shadow. Arrays are front to back
// (CGWindowList order). Bounds are in points, origin top-left of the main display.
import AppKit
import CoreGraphics
import Foundation

var watch = false, apps = false, hz = 30.0
var args = CommandLine.arguments.dropFirst()
while let a = args.popFirst() {
  switch a {
  case "--watch": watch = true
  case "--apps": apps = true
  case "--hz":
    guard let v = args.popFirst().flatMap(Double.init), v > 0, v <= 240 else {
      FileHandle.standardError.write("winlist: --hz needs a number in (0, 240]\n".data(using: .utf8)!)
      exit(2)
    }
    hz = v
  case "-h", "--help":
    print("usage: winlist [--apps] [--watch [--hz N]]"); exit(0)
  default:
    FileHandle.standardError.write("winlist: unknown argument \(a)\n".data(using: .utf8)!)
    exit(2)
  }
}

struct Rect: Codable, Equatable { var x, y, w, h: Double }
struct Win: Codable, Equatable {
  var id: Int
  var pid: Int
  var owner: String?
  var bundle: String?
  var layer: Int
  var bounds: Rect
  var alpha: Double
  var onscreen: Bool
  var title: String?
}
struct Display: Codable, Equatable {
  var id: UInt32
  var w, h: Double  // points
  var pw, ph: Int  // pixels of the current mode
  var scale: Double
}
struct Snapshot: Codable, Equatable {
  var display: Display
  var windows: [Win]
  var overlays: [Win]?
}

// Owners whose windows are never app content (Dock, menu bar extras, desktop, notifications).
let systemOwners: Set<String> = [
  "Dock", "Window Server", "WindowManager", "SystemUIServer", "Control Center",
  "Notification Center", "Spotlight", "TextInputMenuAgent", "Wallpaper", "loginwindow",
]

var bundleCache: [Int: String?] = [:]
func bundleID(_ pid: Int) -> String? {
  if let b = bundleCache[pid] { return b }
  let b = NSRunningApplication(processIdentifier: pid_t(pid))?.bundleIdentifier
  bundleCache[pid] = b
  return b
}

func display() -> Display {
  let id = CGMainDisplayID()
  let b = CGDisplayBounds(id)
  var pw = Int(b.width), ph = Int(b.height)
  if let m = CGDisplayCopyDisplayMode(id) { pw = m.pixelWidth; ph = m.pixelHeight }
  let scale = b.width > 0 ? Double(pw) / Double(b.width) : 1
  return Display(id: id, w: Double(b.width), h: Double(b.height), pw: pw, ph: ph, scale: scale)
}

func snapshot() -> Snapshot? {
  guard let raw = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
    as? [[String: Any]]
  else { return nil }
  var all: [Win] = []
  for d in raw {
    let r = (d[kCGWindowBounds as String] as? NSDictionary)
      .flatMap { CGRect(dictionaryRepresentation: $0 as CFDictionary) } ?? .zero
    let pid = (d[kCGWindowOwnerPID as String] as? Int) ?? -1
    let title = d[kCGWindowName as String] as? String
    all.append(Win(
      id: (d[kCGWindowNumber as String] as? Int) ?? 0,
      pid: pid,
      owner: d[kCGWindowOwnerName as String] as? String,
      bundle: bundleID(pid),
      layer: (d[kCGWindowLayer as String] as? Int) ?? 0,
      bounds: Rect(x: Double(r.origin.x), y: Double(r.origin.y), w: Double(r.width), h: Double(r.height)),
      alpha: (d[kCGWindowAlpha as String] as? Double) ?? 1,
      onscreen: (d[kCGWindowIsOnscreen as String] as? Bool) ?? false,
      title: (title?.isEmpty ?? true) ? nil : title))
  }
  if !apps { return Snapshot(display: display(), windows: all, overlays: nil) }
  let isSystem = { (w: Win) in systemOwners.contains(w.owner ?? "") }
  let sized = { (w: Win) in w.bounds.w > 1 && w.bounds.h > 1 }
  // talagentd draws placeholder copies of restored windows under the app's owner
  // name; they sit exactly under the real window, so they are never content.
  let main = all.filter { $0.layer == 0 && sized($0) && !isSystem($0) && $0.bundle != "com.apple.talagent" }
  let pids = Set(main.map(\.pid))
  // Permission prompts (TCC "wants access to control ...") belong to UserNotificationCenter,
  // not to the app, but block it until answered, so they count as its overlays.
  let over = all.filter {
    sized($0) && (($0.layer != 0 && pids.contains($0.pid)) || $0.bundle == "com.apple.UserNotificationCenter")
  }
  return Snapshot(display: display(), windows: main, overlays: over)
}

let enc = JSONEncoder()
enc.outputFormatting = [.sortedKeys]

// A write to a closed pipe ends the program quietly (exit 0), not with SIGPIPE.
signal(SIGPIPE, SIG_IGN)
func emit(_ s: Snapshot, seq: Int?) {
  guard var data = try? enc.encode(s), var obj = String(data: data, encoding: .utf8) else { return }
  if let seq {  // prefix t (ms since epoch) and seq without re-encoding the snapshot
    let t = Int(Date().timeIntervalSince1970 * 1000)
    obj = "{\"seq\":\(seq),\"t\":\(t)," + obj.dropFirst()
  }
  data = (obj + "\n").data(using: .utf8)!
  let ok = data.withUnsafeBytes { fwrite($0.baseAddress, 1, data.count, stdout) } == data.count
  if !ok || fflush(stdout) != 0 { exit(0) }
}

if !watch {
  guard let s = snapshot() else {
    FileHandle.standardError.write("winlist: no window list (no WindowServer session?)\n".data(using: .utf8)!)
    exit(1)
  }
  emit(s, seq: nil)
  exit(0)
}

var sigSources: [DispatchSourceSignal] = []  // kept alive for the whole run
for sig in [SIGTERM, SIGINT, SIGHUP] {
  signal(sig, SIG_IGN)
  let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
  src.setEventHandler { exit(0) }
  src.resume()
  sigSources.append(src)
}
let parent0 = getppid()
// Level-triggered EVFILT_WRITE on stdout; registration fails for regular files,
// which have no reader to lose, and then the check is skipped.
let kq = kqueue()
var outEv = kevent(ident: 1, filter: Int16(EVFILT_WRITE), flags: UInt16(EV_ADD), fflags: 0, data: 0, udata: nil)
let kqOK = kq >= 0 && kevent(kq, &outEv, 1, nil, 0, nil) == 0
func readerGone() -> Bool {
  guard kqOK else { return false }
  var ev = kevent(), zero = timespec(tv_sec: 0, tv_nsec: 0)
  return kevent(kq, nil, 0, &ev, 1, &zero) == 1 && (Int32(ev.flags) & EV_EOF) != 0
}
var last: Snapshot?
var seq = 0
let timer = DispatchSource.makeTimerSource(queue: .main)
timer.schedule(deadline: .now(), repeating: 1.0 / hz, leeway: .milliseconds(1))
timer.setEventHandler {
  // The reader went away (ssh client killed, `| head` done): with no window change
  // nothing is written, so no EPIPE, and poll() gives no POLLHUP for a pipe on
  // macOS. kqueue reports EV_EOF on the write end; being reparented (sshd-session
  // gone) is the second sign.
  if readerGone() || getppid() != parent0 { exit(0) }
  guard let s = snapshot() else { return }
  if s != last {
    last = s
    emit(s, seq: seq)
    seq += 1
  }
}
timer.resume()
dispatchMain()
