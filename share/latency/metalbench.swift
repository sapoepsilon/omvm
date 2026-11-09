// metalbench: per-command-buffer round trip and throughput on the guest's Metal device.
// usage: metalbench [iterations]   prints one line per test: median / p90 / max ms or a rate.
import Metal
import Foundation
setvbuf(stdout, nil, _IOLBF, 0)
let N = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1])! : 200
let dev = MTLCreateSystemDefaultDevice()!
let q = dev.makeCommandQueue()!
print("device: \(dev.name)")
func now() -> Double { CFAbsoluteTimeGetCurrent() }
func stats(_ name: String, _ a: [Double]) {
    let s = a.sorted()
    print(String(format: "%-28@ n=%d median %.3f p90 %.3f max %.3f ms", name as NSString, s.count,
                 s[s.count / 2] * 1000, s[Int(Double(s.count) * 0.9)] * 1000, s.last! * 1000))
}
let src = """
#include <metal_stdlib>
using namespace metal;
kernel void saxpy(device float *y [[buffer(0)]], device const float *x [[buffer(1)]],
                  constant float &a [[buffer(2)]], uint i [[thread_position_in_grid]]) { y[i] = a * x[i] + y[i]; }
kernel void fma_loop(device float *y [[buffer(0)]], uint i [[thread_position_in_grid]]) {
    float v = float(i) * 1e-6, w = 1.0001;
    for (int k = 0; k < 1024; k++) { v = fma(v, w, 0.5); w = fma(w, 0.9999, 0.0001); }
    y[i] = v + w;
}
struct VOut { float4 pos [[position]]; float4 col; };
vertex VOut vs(uint vid [[vertex_id]], uint iid [[instance_id]]) {
    float2 p[3] = { float2(-1, -1), float2(1, -1), float2(0, 1) };
    VOut o; o.pos = float4(p[vid] * 0.9, 0, 1); o.col = float4(fract(iid * 0.013), 0.5, 0.2, 0.02); return o;
}
fragment float4 fs(VOut in [[stage_in]]) { return in.col; }
"""
let lib = try! dev.makeLibrary(source: src, options: nil)
let saxpy = try! dev.makeComputePipelineState(function: lib.makeFunction(name: "saxpy")!)
let fmaP = try! dev.makeComputePipelineState(function: lib.makeFunction(name: "fma_loop")!)
let rpd = MTLRenderPipelineDescriptor()
rpd.vertexFunction = lib.makeFunction(name: "vs"); rpd.fragmentFunction = lib.makeFunction(name: "fs")
rpd.colorAttachments[0].pixelFormat = .bgra8Unorm
rpd.colorAttachments[0].isBlendingEnabled = true
rpd.colorAttachments[0].sourceRGBBlendFactor = .sourceAlpha
rpd.colorAttachments[0].destinationRGBBlendFactor = .oneMinusSourceAlpha
let rps = try! dev.makeRenderPipelineState(descriptor: rpd)
func tex(_ w: Int, _ h: Int) -> MTLTexture {
    let d = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .bgra8Unorm, width: w, height: h, mipmapped: false)
    d.usage = [.renderTarget, .shaderRead]; d.storageMode = .private
    return dev.makeTexture(descriptor: d)!
}
let small = tex(64, 64), big = tex(1920, 1080)
let n = 1 << 24
let bx = dev.makeBuffer(length: n * 4, options: .storageModeShared)!
let by = dev.makeBuffer(length: n * 4, options: .storageModeShared)!
let bp = dev.makeBuffer(length: 256 << 20, options: .storageModePrivate)!
let bq = dev.makeBuffer(length: 256 << 20, options: .storageModePrivate)!
var a: Float = 2
func render(_ cb: MTLCommandBuffer, _ t: MTLTexture, _ inst: Int) {
    let p = MTLRenderPassDescriptor()
    p.colorAttachments[0].texture = t; p.colorAttachments[0].loadAction = .clear; p.colorAttachments[0].storeAction = .store
    let e = cb.makeRenderCommandEncoder(descriptor: p)!
    if inst > 0 { e.setRenderPipelineState(rps); e.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3, instanceCount: inst) }
    e.endEncoding()
}
func rt(_ name: String, _ body: (MTLCommandBuffer) -> Void) {
    for _ in 0..<5 { let cb = q.makeCommandBuffer()!; body(cb); cb.commit(); cb.waitUntilCompleted() }
    var a: [Double] = [], g: [Double] = []
    for _ in 0..<N {
        let cb = q.makeCommandBuffer()!; body(cb)
        let t0 = now(); cb.commit(); cb.waitUntilCompleted(); a.append(now() - t0)
        if cb.gpuEndTime > 0 { g.append(cb.gpuEndTime - cb.gpuStartTime) }
        if cb.status != .completed { print("\(name): status \(cb.status.rawValue) \(String(describing: cb.error))") }
    }
    stats(name + " rt", a)
    if !g.isEmpty { stats(name + " gpu", g) }
}
rt("empty") { _ in }
rt("compute 1 group") { cb in let e = cb.makeComputeCommandEncoder()!; e.setComputePipelineState(saxpy)
    e.setBuffer(by, offset: 0, index: 0); e.setBuffer(bx, offset: 0, index: 1); e.setBytes(&a, length: 4, index: 2)
    e.dispatchThreads(MTLSize(width: 64, height: 1, depth: 1), threadsPerThreadgroup: MTLSize(width: 64, height: 1, depth: 1)); e.endEncoding() }
rt("render clear 64x64") { cb in render(cb, small, 0) }
rt("render 1 tri 64x64") { cb in render(cb, small, 1) }
rt("blit 4KB") { cb in let e = cb.makeBlitCommandEncoder()!; e.copy(from: bp, sourceOffset: 0, to: bq, destinationOffset: 0, size: 4096); e.endEncoding() }
// shared-buffer readback: CPU write, GPU saxpy, CPU read (a frame of compute in an app)
rt("compute+cpu touch 64KB") { cb in
    by.contents().storeBytes(of: 1, as: Float.self)
    let e = cb.makeComputeCommandEncoder()!; e.setComputePipelineState(saxpy)
    e.setBuffer(by, offset: 0, index: 0); e.setBuffer(bx, offset: 0, index: 1); e.setBytes(&a, length: 4, index: 2)
    e.dispatchThreads(MTLSize(width: 16384, height: 1, depth: 1), threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1)); e.endEncoding() }
// pipelined: many command buffers in flight, wait for the last
func pipelined(_ name: String, _ k: Int, _ body: (MTLCommandBuffer) -> Void) {
    var best = Double.infinity
    for _ in 0..<3 {
        let t0 = now(); var last: MTLCommandBuffer? = nil
        for _ in 0..<k { let cb = q.makeCommandBuffer()!; body(cb); cb.commit(); last = cb }
        last!.waitUntilCompleted(); best = min(best, now() - t0)
    }
    print(String(format: "%-28@ %d cbs in %.1f ms = %.3f ms/cb, %.0f cb/s", name as NSString, k, best * 1000, best * 1000 / Double(k), Double(k) / best))
}
pipelined("pipelined empty", 500) { _ in }
pipelined("pipelined render 1080p", 300) { cb in render(cb, big, 1) }
// cold pipelines: a shader the host has never seen, compiled in the guest, then its first use
// (the host translates it then); and the same pipeline's second use
do {
    let salt = UInt64(Date().timeIntervalSince1970 * 1000)
    var mk: [Double] = [], first: [Double] = [], second: [Double] = []
    for k in 0..<12 {
        let s = """
        #include <metal_stdlib>
        using namespace metal;
        struct VO { float4 pos [[position]]; };
        vertex VO v\(k)(uint vid [[vertex_id]]) { float2 p[3] = { float2(-1,-1), float2(1,-1), float2(0,1) }; VO o; o.pos = float4(p[vid] * \(Double(salt % 1000 + UInt64(k)) / 2000.0), 0, 1); return o; }
        fragment float4 f\(k)(VO in [[stage_in]]) { float x = in.pos.x * \(salt % 977 + UInt64(k)).0; for (int i = 0; i < 4; i++) x = sin(x) * 1.7 + cos(x * 0.3); return float4(x, 0.5, \(k).0 / 12.0, 1); }
        kernel void c\(k)(device float *y [[buffer(0)]], uint i [[thread_position_in_grid]]) { y[i] = y[i] * \(salt % 991 + UInt64(k)).0 + sin(float(i)); }
        """
        let t0 = now()
        let l = try! dev.makeLibrary(source: s, options: nil)
        let d = MTLRenderPipelineDescriptor(); d.vertexFunction = l.makeFunction(name: "v\(k)"); d.fragmentFunction = l.makeFunction(name: "f\(k)")
        d.colorAttachments[0].pixelFormat = .bgra8Unorm
        let ps = try! dev.makeRenderPipelineState(descriptor: d)
        let cs = try! dev.makeComputePipelineState(function: l.makeFunction(name: "c\(k)")!)
        mk.append(now() - t0)
        for pass in 0..<2 {
            let cb = q.makeCommandBuffer()!
            let p = MTLRenderPassDescriptor(); p.colorAttachments[0].texture = small; p.colorAttachments[0].loadAction = .clear; p.colorAttachments[0].storeAction = .store
            let e = cb.makeRenderCommandEncoder(descriptor: p)!; e.setRenderPipelineState(ps); e.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3); e.endEncoding()
            let c = cb.makeComputeCommandEncoder()!; c.setComputePipelineState(cs); c.setBuffer(by, offset: 0, index: 0)
            c.dispatchThreads(MTLSize(width: 64, height: 1, depth: 1), threadsPerThreadgroup: MTLSize(width: 64, height: 1, depth: 1)); c.endEncoding()
            let t1 = now(); cb.commit(); cb.waitUntilCompleted()
            (pass == 0 ? { first.append(now() - t1) } : { second.append(now() - t1) })()
        }
    }
    stats("new pipeline: guest compile", mk); stats("new pipeline: first use rt", first); stats("new pipeline: second use rt", second)
}
// throughput
func timed(_ name: String, _ reps: Int, _ unit: Double, _ uname: String, _ body: (MTLCommandBuffer) -> Void) {
    var best = Double.infinity
    for _ in 0..<4 { let cb = q.makeCommandBuffer()!; for _ in 0..<reps { body(cb) }
        let t0 = now(); cb.commit(); cb.waitUntilCompleted(); best = min(best, now() - t0) }
    print(String(format: "%-28@ %.2f ms, %.1f %@", name as NSString, best * 1000, unit * Double(reps) / best, uname as NSString))
}
timed("saxpy 64MB x10", 10, Double(n * 12) / 1e9, "GB/s") { cb in let e = cb.makeComputeCommandEncoder()!; e.setComputePipelineState(saxpy)
    e.setBuffer(by, offset: 0, index: 0); e.setBuffer(bx, offset: 0, index: 1); e.setBytes(&a, length: 4, index: 2)
    e.dispatchThreads(MTLSize(width: n, height: 1, depth: 1), threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1)); e.endEncoding() }
timed("fma 16M thr x2048 flop", 4, Double(n) * 2048 / 1e9, "GFLOP/s") { cb in let e = cb.makeComputeCommandEncoder()!; e.setComputePipelineState(fmaP)
    e.setBuffer(by, offset: 0, index: 0)
    e.dispatchThreads(MTLSize(width: n, height: 1, depth: 1), threadsPerThreadgroup: MTLSize(width: 256, height: 1, depth: 1)); e.endEncoding() }
timed("blit 256MB x4", 4, 2 * 256.0 * 1048576 / 1e9, "GB/s") { cb in let e = cb.makeBlitCommandEncoder()!
    e.copy(from: bp, sourceOffset: 0, to: bq, destinationOffset: 0, size: 256 << 20); e.endEncoding() }
timed("render 1080p 2000 inst x20", 20, 1920.0 * 1080 * 0.405 * 2000 / 1e9, "Gpix/s") { cb in render(cb, big, 2000) }
