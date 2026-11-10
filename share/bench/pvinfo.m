// Dump what the guest's paravirtual Metal driver holds about the host device.
#import <Metal/Metal.h>
#import <objc/runtime.h>

static void dumpIvar(id obj, const char *name, size_t bytes) {
  Ivar iv = class_getInstanceVariable(object_getClass(obj), name);
  if (!iv) { printf("%s: no ivar\n", name); return; }
  ptrdiff_t off = ivar_getOffset(iv);
  const uint32_t *p = (const uint32_t *)((const uint8_t *)(__bridge void *)obj + off);
  printf("%s @+%td type %.60s:\n", name, off, ivar_getTypeEncoding(iv));
  for (size_t i = 0; i < bytes / 4; i++) printf("%s%08x", i % 8 ? " " : "\n  ", p[i]);
  printf("\n");
}

int main(void) {
  @autoreleasepool {
    id<MTLDevice> d = MTLCreateSystemDefaultDevice();
    NSObject *o = (NSObject *)d;
    printf("class %s\n", object_getClassName(o));
    for (Class c = object_getClass(o); c; c = class_getSuperclass(c)) printf("  isa %s\n", class_getName(c));
    NSArray *keys = @[@"featureProfile", @"supportsMeshShaders", @"requiresMeshShaderEmulation",
      @"requiresRaytracingEmulation", @"supportsRaytracing", @"supportsSparseTextures", @"supportsSparseHeaps",
      @"supportsPlacementSparse", @"supportsArgumentBuffersTier2", @"supportsFunctionPointers",
      @"supportsDynamicLibraries", @"supportsMeshShadersInICB", @"supportsBinaryArchives", @"supportsGPUFamilyMetal3",
      @"supportsOpenGL", @"supportsLateEvalEvent", @"supportsFastMathInfNaNPropagation"];
    for (NSString *k in keys) {
      @try { printf("%s = %s\n", k.UTF8String, [[[o valueForKey:k] description] UTF8String]); }
      @catch (NSException *e) { printf("%s: (no key)\n", k.UTF8String); }
    }
    // The device-info struct: named u32 slots in the host's key order.
    Ivar iv = class_getInstanceVariable(object_getClass(o), "_deviceInfo");
    if (iv) {
      const char *enc = ivar_getTypeEncoding(iv);
      ptrdiff_t off = ivar_getOffset(iv);
      const uint32_t *p = (const uint32_t *)((const uint8_t *)(__bridge void *)o + off);
      // The encoding lists "Name"(?="u"I"f"f) per slot.
      const char *s = enc; int i = 0;
      while ((s = strchr(s, '"'))) {
        const char *e = strchr(s + 1, '"'); if (!e) break;
        if (e[1] == '(') { printf("  [%2d] %.*s = %u (0x%x)\n", i, (int)(e - s - 1), s + 1, p[i], p[i]); i++; }
        s = e + 1;
      }
    }
    dumpIvar(o, "_features", 32);
    dumpIvar(o, "_supportedHostFamilies", 8);
    Ivar hf = class_getInstanceVariable(object_getClass(o), "_supportedHostFamilies");
    if (hf) {
      void *ptr = *(void **)((uint8_t *)(__bridge void *)o + ivar_getOffset(hf));
      if (ptr) { const uint32_t *q = ptr; printf("  -> "); for (int i = 0; i < 16; i++) printf("%08x ", q[i]); printf("\n"); }
    }
    int fams[] = {1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,2002,3001,3002,3003,5001,5002};
    for (int i = 0; i < 16; i++) printf("supportsFamily(%d)=%d ", fams[i], [d supportsFamily:fams[i]]);
    printf("\n");
  }
  return 0;
}
