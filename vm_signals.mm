#include <Metal/Metal.h>
#include <sys/sysctl.h>
#include <cstdio>
#include <string>

static std::string sysctl_str(const char* name) {
  size_t len = 0;
  if (sysctlbyname(name, nullptr, &len, nullptr, 0) != 0) return "<unavailable>";
  std::string rc(len, '\0');
  sysctlbyname(name, rc.data(), &len, nullptr, 0);
  return rc.c_str();
}

static std::string sysctl_int(const char* name) {
  int32_t v = 0; size_t len = sizeof(v);
  if (sysctlbyname(name, &v, &len, nullptr, 0) != 0) return "<unavailable>";
  return std::to_string(v);
}

int main() {
  @autoreleasepool {
    printf("kern.hv_vmm_present      : %s\n", sysctl_int("kern.hv_vmm_present").c_str());
    printf("machdep.cpu.brand_string : %s\n", sysctl_str("machdep.cpu.brand_string").c_str());
    printf("hw.model                 : %s\n", sysctl_str("hw.model").c_str());
    id<MTLDevice> d = MTLCreateSystemDefaultDevice();
    printf("MTLDevice.name           : %s\n", d.name.UTF8String);
    if (@available(macOS 14.0, *)) {
      printf("MTLDevice.architecture   : %s\n", d.architecture.name.UTF8String);
    }
    printf("isLowPower/Headless/Remov: %d/%d/%d\n", d.isLowPower, d.isHeadless, d.isRemovable);
    printf("recommendedMaxWorkingSet : %.1f GB\n", d.recommendedMaxWorkingSetSize / 1e9);
    for (int f : {1007, 1008, 1009, 1010}) {
      printf("supportsFamily Apple%d    : %d\n", f - 1000, [d supportsFamily:(MTLGPUFamily)f]);
    }
  }
}
