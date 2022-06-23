#include <Metal/Metal.h>

int main() {
  @autoreleasepool {
     NSArray* devices = [MTLCopyAllDevices() autorelease];
     NSLog(@"Metal device count %lu", devices.count);
     for (unsigned long i = 0 ; i < devices.count ; i++) {
        id<MTLDevice>  device = devices[i];
        NSLog(@"Found device %@ isLowPower %s", device.name, device.isLowPower ? "true" : "false");
     }
  }
}
