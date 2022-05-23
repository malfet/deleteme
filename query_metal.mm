#include <Metal/Metal.h>

int main() {
  @autoreleasepool {
     NSArray* devices = [MTLCopyAllDevices() autorelease];
     for (unsigned long i = 0 ; i < [devices count] ; i++) {
        id<MTLDevice>  device = devices[i];
        NSLog(@"Found device %@ isLowPower %s", device.name, device.isLowPower ? "true" : "false");
     }
  }
}
