#include <Metal/Metal.h>

#include <stdexcept>
#include <string>

id<MTLDevice> getMetalDevice() {
  NSArray *devices = [MTLCopyAllDevices() autorelease];
  NSLog(@"Metal device count %lu", devices.count);
  if (devices.count == 0) {
    throw std::runtime_error("Metal is not supported");
  }
  // Print some info
  for (unsigned long i = 0 ; i < devices.count ; i++) {
    id<MTLDevice>  device = devices[i];
    NSLog(@"Found device %@ isLowPower %s supports Metal %s",
          device.name,
          device.isLowPower ? "true" : "false",
          [device supportsFamily:MTLGPUFamilyMac2] ? "true" : "false");
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
