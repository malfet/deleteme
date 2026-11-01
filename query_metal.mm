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

int main() {
  @autoreleasepool {
    id<MTLDevice> dev = getMetalDevice();
    auto buf_C = allocSharedBuffer(dev, 1024 * 1024);
  }
}
