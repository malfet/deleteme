#include <Metal/Metal.h>

#include <stdexcept>
#include <string>

// Raw MTLGPUFamily values, so that families missing from older SDKs can still
// be queried (supportsFamily simply returns NO for unknown values)
static const struct {
  const char *name;
  NSInteger value;
} kGPUFamilies[] = {
    {"Apple1", 1001},   {"Apple2", 1002},  {"Apple3", 1003},
    {"Apple4", 1004},   {"Apple5", 1005},  {"Apple6", 1006},
    {"Apple7", 1007},   {"Apple8", 1008},  {"Apple9", 1009},
    {"Apple10", 1010},  {"Mac1", 2001},    {"Mac2", 2002},
    {"Common1", 3001},  {"Common2", 3002}, {"Common3", 3003},
    {"MacCatalyst1", 4001}, {"MacCatalyst2", 4002},
    {"Metal3", 5001},   {"Metal4", 5002},
};

static const char *yesno(BOOL v) { return v ? "true" : "false"; }

static void dumpDevice(id<MTLDevice> device) {
  NSLog(@"=== Device: %@", device.name);
  if (@available(macOS 14.0, *)) {
    NSLog(@"  architecture: %@", device.architecture.name);
  }
  NSLog(@"  registryID: 0x%llx", device.registryID);
  NSLog(@"  isLowPower: %s isHeadless: %s isRemovable: %s hasUnifiedMemory: %s",
        yesno(device.isLowPower), yesno(device.isHeadless),
        yesno(device.isRemovable), yesno(device.hasUnifiedMemory));
  NSLog(@"  recommendedMaxWorkingSetSize: %llu MB maxBufferLength: %lu MB",
        device.recommendedMaxWorkingSetSize >> 20,
        (unsigned long)(device.maxBufferLength >> 20));
  NSLog(@"  maxThreadgroupMemoryLength: %lu maxThreadsPerThreadgroup: %lux%lux%lu",
        (unsigned long)device.maxThreadgroupMemoryLength,
        (unsigned long)device.maxThreadsPerThreadgroup.width,
        (unsigned long)device.maxThreadsPerThreadgroup.height,
        (unsigned long)device.maxThreadsPerThreadgroup.depth);
  NSLog(@"  argumentBuffersSupport: tier%lu readWriteTextureSupport: tier%lu",
        (unsigned long)device.argumentBuffersSupport + 1,
        (unsigned long)device.readWriteTextureSupport);
  NSLog(@"  supportsRaytracing: %s supportsFunctionPointers: %s "
        @"supportsDynamicLibraries: %s supports32BitFloatFiltering: %s "
        @"supportsBCTextureCompression: %s",
        yesno(device.supportsRaytracing), yesno(device.supportsFunctionPointers),
        yesno(device.supportsDynamicLibraries),
        yesno(device.supports32BitFloatFiltering),
        yesno(device.supportsBCTextureCompression));
  for (const auto &f : kGPUFamilies) {
    NSLog(@"  supportsFamily(%-12s = %ld): %s", f.name, (long)f.value,
          yesno([device supportsFamily:(MTLGPUFamily)f.value]));
  }
}

id<MTLDevice> getMetalDevice() {
  NSArray *devices = [MTLCopyAllDevices() autorelease];
  NSLog(@"OS version: %@", [[NSProcessInfo processInfo] operatingSystemVersionString]);
  NSLog(@"Metal device count %lu", devices.count);
  if (devices.count == 0) {
    throw std::runtime_error("Metal is not supported");
  }
  for (unsigned long i = 0 ; i < devices.count ; i++) {
    dumpDevice(devices[i]);
  }
  return devices[0];
}

id<MTLBuffer> allocSharedBuffer(id<MTLDevice> device, unsigned length) {
  id<MTLBuffer> rc = [device newBufferWithLength:length
                                         options:MTLResourceStorageModeShared];
  if (rc == nil) {
    throw std::runtime_error("Can't allocate " + std::to_string(length) +
                             " bytes on GPU");
  }
  return rc;
}

// Uses bfloat (MSL 3.1) and shader logging (MSL 3.2)
static NSString *kMetal32Shader = @R"MTL(
#include <metal_stdlib>
#include <metal_logging>
using namespace metal;

constant os_log logger("query_metal", "metal32");

kernel void metal32_test(device float* out [[buffer(0)]],
                         uint tid [[thread_position_in_grid]]) {
  bfloat x = bfloat(tid) * bfloat(0.5);
  out[tid] = float(x) + float(__METAL_VERSION__);
  if (tid == 1) {
    logger.log("hello from metal %d, tid %u, bfloat %f", __METAL_VERSION__, tid, float(x));
  }
}
)MTL";

static void runMetal32Test(id<MTLDevice> dev) {
  if (@available(macOS 15.0, *)) {
    NSError *err = nil;
    MTLCompileOptions *opts = [[MTLCompileOptions new] autorelease];
    opts.languageVersion = (MTLLanguageVersion)((3 << 16) + 2);
    opts.enableLogging = YES;
    id<MTLLibrary> lib = [dev newLibraryWithSource:kMetal32Shader options:opts error:&err];
    if (lib == nil) {
      NSLog(@"Metal 3.2 compile FAILED: %@", err.localizedDescription);
      return;
    }
    NSLog(@"Metal 3.2 compile succeeded");
    id<MTLFunction> fn = [[lib newFunctionWithName:@"metal32_test"] autorelease];
    id<MTLComputePipelineState> pso = [dev newComputePipelineStateWithFunction:fn error:&err];
    if (pso == nil) {
      NSLog(@"Metal 3.2 pipeline creation FAILED: %@", err.localizedDescription);
      return;
    }

    MTLLogStateDescriptor *logDesc = [[MTLLogStateDescriptor new] autorelease];
    logDesc.level = MTLLogLevelDebug;
    id<MTLLogState> logState = [dev newLogStateWithDescriptor:logDesc error:&err];
    if (logState == nil) {
      NSLog(@"Failed to create log state: %@", err.localizedDescription);
      return;
    }
    [logState addLogHandler:^(NSString *subsystem, NSString *category,
                              MTLLogLevel level, NSString *message) {
      NSLog(@"Shader log [%@/%@]: %@", subsystem, category, message);
    }];
    MTLCommandQueueDescriptor *qDesc = [[MTLCommandQueueDescriptor new] autorelease];
    qDesc.logState = logState;
    id<MTLCommandQueue> queue = [dev newCommandQueueWithDescriptor:qDesc];

    constexpr unsigned N = 4;
    auto buf = allocSharedBuffer(dev, N * sizeof(float));
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
    [enc setComputePipelineState:pso];
    [enc setBuffer:buf offset:0 atIndex:0];
    [enc dispatchThreads:MTLSizeMake(N, 1, 1) threadsPerThreadgroup:MTLSizeMake(N, 1, 1)];
    [enc endEncoding];
    [cb commit];
    [cb waitUntilCompleted];
    if (cb.error) {
      NSLog(@"Metal 3.2 dispatch FAILED: %@", cb.error.localizedDescription);
      return;
    }
    auto out = static_cast<float *>(buf.contents);
    bool ok = true;
    for (unsigned i = 0; i < N; ++i) {
      ok &= out[i] == 320.0f + 0.5f * i;
    }
    NSLog(@"Metal 3.2 dispatch results: %g %g %g %g -> %s", out[0], out[1], out[2],
          out[3], ok ? "OK" : "MISMATCH");
  } else {
    NSLog(@"Metal 3.2 requires macOS 15+, skipping");
  }
}

int main() {
  @autoreleasepool {
    id<MTLDevice> dev = getMetalDevice();
    auto buf_C = allocSharedBuffer(dev, 1024 * 1024);
    runMetal32Test(dev);
  }
}
