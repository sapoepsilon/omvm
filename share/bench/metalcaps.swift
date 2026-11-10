import Metal
import Foundation

guard let d = MTLCreateSystemDefaultDevice() else { print("{\"error\":\"no device\"}"); exit(1) }
var o: [String: Any] = [:]
o["name"] = d.name
o["os"] = ProcessInfo.processInfo.operatingSystemVersionString
var fam: [String: Bool] = [:]
let fams: [(String, MTLGPUFamily)] = [
  ("apple1", .apple1), ("apple2", .apple2), ("apple3", .apple3), ("apple4", .apple4),
  ("apple5", .apple5), ("apple6", .apple6), ("apple7", .apple7), ("apple8", .apple8),
  ("apple9", .apple9), ("mac2", .mac2), ("common1", .common1), ("common2", .common2),
  ("common3", .common3), ("metal3", .metal3),
]
for (n, f) in fams { fam[n] = d.supportsFamily(f) }
if let a10 = MTLGPUFamily(rawValue: 1010) { fam["apple10"] = d.supportsFamily(a10) }
if let m4 = MTLGPUFamily(rawValue: 5002) { fam["metal4"] = d.supportsFamily(m4) }
o["families"] = fam
var f: [String: Any] = [:]
f["supportsRaytracing"] = d.supportsRaytracing
f["supportsRaytracingFromRender"] = d.supportsRaytracingFromRender
f["supportsFunctionPointers"] = d.supportsFunctionPointers
f["supportsFunctionPointersFromRender"] = d.supportsFunctionPointersFromRender
f["supportsPrimitiveMotionBlur"] = d.supportsPrimitiveMotionBlur
f["supportsDynamicLibraries"] = d.supportsDynamicLibraries
f["supportsRenderDynamicLibraries"] = d.supportsRenderDynamicLibraries
f["supports32BitMSAA"] = d.supports32BitMSAA
f["supports32BitFloatFiltering"] = d.supports32BitFloatFiltering
f["supportsBCTextureCompression"] = d.supportsBCTextureCompression
f["supportsQueryTextureLOD"] = d.supportsQueryTextureLOD
f["supportsPullModelInterpolation"] = d.supportsPullModelInterpolation
f["supportsShaderBarycentricCoordinates"] = d.supportsShaderBarycentricCoordinates
f["argumentBuffersSupport"] = d.argumentBuffersSupport.rawValue
f["readWriteTextureSupport"] = d.readWriteTextureSupport.rawValue
f["hasUnifiedMemory"] = d.hasUnifiedMemory
f["maxBufferLength"] = d.maxBufferLength
f["recommendedMaxWorkingSetSize"] = d.recommendedMaxWorkingSetSize
f["supportsCounterSampling_stage"] = d.supportsCounterSampling(.atStageBoundary)
f["sparseTileSizeInBytes"] = d.sparseTileSizeInBytes
f["maxArgumentBufferSamplerCount"] = d.maxArgumentBufferSamplerCount
f["supportsVertexAmplification2"] = d.supportsVertexAmplificationCount(2)
f["supportsRasterizationRateMap1"] = d.supportsRasterizationRateMap(layerCount: 1)
f["depth24Stencil8"] = d.isDepth24Stencil8PixelFormatSupported
f["programmableSamplePositions"] = d.areProgrammableSamplePositionsSupported
f["rasterOrderGroups"] = d.areRasterOrderGroupsSupported
f["maxThreadgroupMemoryLength"] = d.maxThreadgroupMemoryLength
f["maxTransferRate"] = d.maxTransferRate
f["architecture"] = d.architecture.name
o["features"] = f

// Functional probes of Metal 3 features: does the device actually make the objects?
var p: [String: Any] = [:]
// mesh shader pipeline
let src = """
#include <metal_stdlib>
using namespace metal;
struct V { float4 pos [[position]]; };
struct P { float c; };
using M = mesh<V, P, 3, 1, topology::triangle>;
[[mesh]] void ms(M out) {
  out.set_primitive_count(1);
  V v; v.pos = float4(0,0,0,1); out.set_vertex(0, v);
  v.pos = float4(1,0,0,1); out.set_vertex(1, v);
  v.pos = float4(0,1,0,1); out.set_vertex(2, v);
  out.set_index(0,0); out.set_index(1,1); out.set_index(2,2);
}
fragment float4 fs() { return float4(1); }
"""
do {
  let lib = try d.makeLibrary(source: src, options: nil)
  let md = MTLMeshRenderPipelineDescriptor()
  md.meshFunction = lib.makeFunction(name: "ms")
  md.fragmentFunction = lib.makeFunction(name: "fs")
  md.colorAttachments[0].pixelFormat = .bgra8Unorm
  do {
    let (st, _) = try d.makeRenderPipelineState(descriptor: md, options: [])
    p["meshPipeline"] = "ok \(st)".prefix(40).description
  } catch { p["meshPipeline"] = "error: \(error.localizedDescription)" }
} catch { p["meshLibrary"] = "error: \(error.localizedDescription)" }
// sparse heap: the paravirtual driver asserts on it, so it runs in a child process
if CommandLine.arguments.count > 1 && CommandLine.arguments[1] == "sparse" {
  let hd = MTLHeapDescriptor()
  hd.type = .sparse
  hd.storageMode = .private
  hd.size = 16 << 20
  print(d.makeHeap(descriptor: hd) != nil ? "sparse-ok" : "sparse-nil")
  exit(0)
}
do {
  let c = Process()
  c.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
  c.arguments = ["sparse"]
  let out = Pipe(); c.standardOutput = out; c.standardError = Pipe()
  try c.run(); c.waitUntilExit()
  let text = String(data: out.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
  p["sparseHeap"] = text.contains("sparse-ok") ? "ok" : (c.terminationReason == .uncaughtSignal ? "driver assertion (signal \(c.terminationStatus))" : "nil")
} catch { p["sparseHeap"] = "error: \(error.localizedDescription)" }
// IO command queue (fast resource loading)
do {
  let q = try d.makeIOCommandQueue(descriptor: MTLIOCommandQueueDescriptor())
  p["ioCommandQueue"] = "ok \(type(of: q))"
} catch { p["ioCommandQueue"] = "error: \(error.localizedDescription)" }
// acceleration structure sizes (ray tracing)
if d.supportsRaytracing {
  let g = MTLAccelerationStructureTriangleGeometryDescriptor()
  g.triangleCount = 1
  let ad = MTLPrimitiveAccelerationStructureDescriptor()
  ad.geometryDescriptors = [g]
  let s = d.accelerationStructureSizes(descriptor: ad)
  p["accelSizes"] = s.accelerationStructureSize
} else { p["accelSizes"] = "n/a (supportsRaytracing false)" }
o["probes"] = p
let data = try! JSONSerialization.data(withJSONObject: o, options: [.prettyPrinted, .sortedKeys])
print(String(data: data, encoding: .utf8)!)
