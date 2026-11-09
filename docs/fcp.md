# Final Cut Pro in the `macos` guest

Running Final Cut Pro (FCP) in the `macos` VM (macOS 27.2 26B123, 8 vCPU, 16 GB,
"Apple Paravirtual device" GPU). The GPU agent polls this file: open GPU gaps are under
**GPU gaps**, each with repro and host log lines.

## Status (2026-11-09)

**Blocked at the licence wall, not the GPU.** FCP 12.4 installs, passes Gatekeeper,
launches and draws its Metal UI, but every path past the first screen needs an Apple
Account, and this VM can't sign in to one (no Secure Enclave attestation). So import,
timeline playback, effects, background render and export inside FCP are untested.
The same media work through AVFoundation + CoreImage on the guest's Metal device does
run, and it found one VM-killing GPU gap (GAP-1) that FCP will hit too.

| Step | Result |
| --- | --- |
| Get the free trial from apple.com | **no**: discontinued (see Install) |
| Install | **yes**: owner's App Store build copied in; `codesign --verify --deep --strict` OK, `spctl`: accepted, source=Mac App Store |
| Launch | **yes**: window up within 12 s (not timed closer); no Metal errors in `log stream`, no crash report |
| Past the welcome screen | **no**: "Unlock Final Cut Pro and more. For $12.99/month." paywall; closing it quits FCP; "Get Creator Studio" opens "Sign in to your Apple Account" |
| New library/project, import, playback, effects, render, export in FCP | **not reached** |
| Same pipeline in AVFoundation/CoreImage (stand-in) | **partial**: 3 exports OK, the 4th killed the VM (GAP-1) |

Screenshots (presigned, 24 h, bucket `whispera-artifacts`, prefix `vm-shots/2026-11-09/`):
`fcp-paywall.png`, `fcp-plans.png`, `fcp-signin.png`.

To finish the FCP test plan, one of these has to change: Apple Account sign-in working in
the guest, or a licensed FCP that does not check a subscription (a one-time-purchase
build whose App Store receipt validates offline). Neither is something the guest side
can do; no cracked builds were tried.

## Numbers (AVFoundation + CoreImage stand-in, same boot, 2026-11-09)

`~/bin/pipe` in the guest (source `~/bin/pipe.swift`): `AVAssetExportSession`, optionally
with an `AVVideoComposition` whose CoreImage handler (a `CIContext` on the Metal device)
applies `CIColorControls` (sat 1.4, contrast 1.1) + `CIGaussianBlur` (r 6) + a 50 %
black lower-third box, standing in for colour correction + blur + title. Sources are 30 s
clips made in the guest with Homebrew ffmpeg 8 (`~/Movies/fcptest`).

| Source | Export | Time | Realtime | Output |
| --- | --- | --- | --- | --- |
| 4K H.264 40 Mb/s (testsrc2) | 1080p H.264 + fx | 26.6 s | 1.13x | 21.6 MB |
| 4K H.264 | 4K H.264 + fx | 30.2 s | 0.99x | 49.2 MB |
| 4K H.264 | ProRes 422 + LPCM + fx | 27.2 s | 1.10x | 584 MB |
| 1080p ProRes 422 10-bit (mandelbrot) | 1080p H.264, no fx | VM crashed | | GAP-1 |

- CPU during the first export (`top`): `VTEncoderXPCService` 112 %, `VTDecoderXPCService`
  98 %, the app 42 %: decode and encode are both software, the CoreImage work is on the
  GPU (the CIContext reports `Apple Paravirtual device`). About 2.5 of 8 vCPUs busy, so
  exports are codec-bound, not GPU-bound.
- Test media generation (ffmpeg, software): 30 s 4K H.264 veryfast in 16 s, 30 s 1080p
  ProRes 422 in 16 s.
- No bare-M1-Max reference measured here, so none given.

## GPU gaps (open)

### GAP-1: VM dies on a compute dispatch that samples `RGBA8Unorm` (AVFoundation ProRes -> H.264 export)

- **Symptom:** the whole VM dies (`shutting down, reason=crashed`) at
  2026-11-09 22:43:50 UTC, during a plain AVFoundation export, no FCP involved.
- **Host log** (`~/.cache/libvirt/qemu/log/macos.log`, line ~5823):

  ```
  reims-vgpu: fatal: platform call dispatchThreadgroups:threadsPerThreadgroup:: the Vulkan runtime refused it: unsupported: Unsupported { feature: Format, needs: AnyOf([[Format { format: VK_FORMAT_R8G8B8A8_UNORM, usage: SampledImage }]]), location: None, symbol: None }
  2026-11-09 22:43:50.775+0000: shutting down, reason=crashed
  ```

- **Repro (guest):** `~/Movies/fcptest/clip1080_prores.mov` (30 s 1920x1080 ProRes 422
  10-bit `yuv422p10le` + PCM, made by `ffmpeg -f lavfi -i mandelbrot=size=1920x1080:rate=30
  -t 30 -c:v prores_ks -profile:v 2 -pix_fmt yuv422p10le`), then
  `/tmp/pipe clip1080_prores.mov out/d_h264.mp4 AVAssetExportPreset1920x1080`
  (`/tmp/pipe` = `AVAssetExportSession` with no video composition; source in
  `/tmp/pipe.swift`). No CIContext, so the kernel is Apple's own: the guest prints
  `IOServiceMatchingfailed for: AppleM2ScalerParavirtDriver` before each export, so
  VideoToolbox's pixel transfer (ProRes 10-bit 4:2:2 -> 8-bit 4:2:0 for the software
  H.264 encoder) falls back to a Metal compute kernel, and that kernel's dispatch is the
  refused call.
- **Ran fine just before it, same boot:** 4K H.264 -> 1080p H.264 / 4K H.264 / ProRes 422
  with a CoreImage (Metal) colour + Gaussian blur + overlay composition (see Numbers).
  So H.264-decoded (8-bit biplanar) inputs pass; a 10-bit ProRes-decoded input does not.
- **Why it matters for FCP:** FCP decodes ProRes and converts pixel formats through the
  same VideoToolbox/Metal path for playback, render and every export, so this is likely
  a VM kill on the first ProRes import/playback.
- **Suggested fix:** the format-feature check for the texture this dispatch binds as
  `RGBA8Unorm` fails. It is probably not an optimal-tiling 2D image (RGBA8 sampled is
  mandatory there) but a linear-tiled image or a texture over a buffer/IOSurface
  (`newTextureWithDescriptor:offset:bytesPerRow:` or an IOSurface-backed CVMetalTexture of
  a 10-bit packed `v210`/`x422` surface viewed as RGBA8). Check `linearTilingFeatures`
  / `bufferFeatures` for `R8G8B8A8_UNORM` on the device and, when SAMPLED is missing,
  copy into an optimal-tiled scratch image (or read through a storage texel buffer)
  instead of refusing. Either way, refusing should fail the command buffer
  (`MTLCommandBufferStatusError`) rather than kill QEMU, so the guest app errors out
  instead of the VM.

## Guest facts

- Not a FCP blocker but worth knowing: the guest prints `IOServiceMatchingfailed for:
  AppleM2ScalerParavirtDriver` on every AVFoundation export, so scaling and pixel-format
  conversion that a Mac does on the hardware scaler run as Metal compute (and hit GAP-1).
- Resources: `hw.memsize` 17169383424 (16 GB), `hw.ncpu` 8, 97 GB free on `/`.
  Enough for FCP (Apple's floor: 8 GB RAM, 6.5 GB disk); 16 GB RAM is Apple's
  recommendation for 4K, so no change requested.
- Metal: `Apple Paravirtual device`, Apple5 + Mac2 families, no Apple7, no Metal 3, no
  ray tracing, `maxBufferLength` 8.0 GiB, `recommendedMaxWorkingSetSize` 10.7 GB.
- VideoToolbox: software only. Encoders listed: H.264 (SW), HEVC (SW), ProRes
  422/HQ/LT/Proxy/4444/XQ (CPU), JPEG. `VTIsHardwareDecodeSupported` is false for H.264,
  HEVC, ProRes 422 and ProRes 4444. No `AppleM2ScalerParavirtDriver` (no hardware scaler).

## Final Cut Pro install

- Apple ended the free 90-day trial on 2026-01-13 with Apple Creator Studio:
  `https://www.apple.com/final-cut-pro/trial/` now 301-redirects to
  `/final-cut-pro/`, whose only "Try it free" links go to the App Store
  (`apps.apple.com/app-bundle/id1868448255`, a 30-day Creator Studio trial that needs an
  Apple Account and payment details). There is no trial DMG any more, and this VM cannot
  sign in to an Apple Account (no Secure Enclave attestation).
- Installed instead: the owner's own App Store copy, "Final Cut Pro Creator Studio.app"
  12.4 (`LSMinimumSystemVersion` 26.6, 6.6 GB), rsynced from the owner's Mac into
  `/Applications` (~7.5 min over the omarchy hop). Its signature and `_MASReceipt` are
  intact; nothing was patched.
- First launch: "Welcome to Final Cut Pro" (Creator Studio) -> Continue -> paywall
  "Unlock Final Cut Pro and more. For $12.99/month." with "Get Creator Studio" and "See All
  Plans" (Monthly $12.99, Annual $129, Education $2.99/mo, $29.99/yr; no trial offered
  without an account). Closing the paywall quits FCP. "Get Creator Studio" opens the
  StoreKit sheet "Sign in to your Apple Account"; cancelled there. `log stream` shows
  `storekitagent` running for `com.apple.FinalCutApp` and `JetEngine` `AmsBagError`
  codes 1 and 2 (no store bag without an account), and no Metal errors.

## How the guest GUI was driven

Guest-side `screencapture` fails over SSH ("could not create image from display": no
Screen Recording grant, and SIP is on so TCC.db can't be edited). Instead: eyes = host
`grim -o eDP-1 -s 0.5` of the full-screen `reims-vgpu` window (1 px = 1 guest point in
local mode at 1512x982), hands = a host `ydotoold` (user socket) on `/dev/uinput`. While
the window has captured input the guest pointer takes relative motion only, so a click
is: `ydotool mousemove -x -1000 -y -1000` (x4, pins it to 0,0), then `mousemove -x X -y
Y`, then `click 0xC0`. Motion is 1:1 (no acceleration seen).
