#include <Metal/Metal.h>

int main() {
  @autoreleasepool {
     NSArray* devices = [MTLCopyAllDevices() autorelease];
     NSLog(@"Metal device count %lu", devices.count);
     for (unsigned long i = 0 ; i < devices.count ; i++) {
        id<MTLDevice>  device = devices[i];
        NSLog(@"Found device %@ isLowPower %s", device.name, device.isLowPower ? "true" : "false");
     }
     id mpsCD = NSClassFromString(@"MPSGraph");
     NSLog(@"mpsCD is %@", mpsCD);
     if ([mpsCD instancesRespondToSelector:@selector
                 (LSTMWithSourceTensor:recurrentWeight:inputWeight:bias:initState:initCell:descriptor:name:)] == NO) {
         NSLog(@"MPS graph is too old");
     }
  }
}
