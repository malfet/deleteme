#include <Metal/Metal.h>
#include <MetalPerformanceShadersGraph/MetalPerformanceShadersGraph.h>

int main() {
  @autoreleasepool {
     NSArray* devices = [MTLCopyAllDevices() autorelease];
     NSLog(@"Metal device count %lu", devices.count);
     for (unsigned long i = 0 ; i < devices.count ; i++) {
        id<MTLDevice>  device = devices[i];
        NSLog(@"Found device %@ isLowPower %s", device.name, device.isLowPower ? "true" : "false");
     }

    if (@available(macOS 12.3, *)) {
       NSLog(@"MacOS available");
    }

    if(@available(macOSApplicationExtension 12.3, *)) {
      NSLog(@"Extension available");
    }
    NSOperatingSystemVersion ver = [[NSProcessInfo processInfo] operatingSystemVersion];
    NSLog(@"OS version %ld.%ld.%ld\n", ver.majorVersion, ver.minorVersion, ver.patchVersion);
  }
}
