# AppArmor profile placeholder for executor sandbox
# Full profile to be implemented in Phase 2.

#include <tunables/global>

profile executor-sandbox flags=(attach_disconnected) {
  #include <abstractions/base>
  deny /proc/** r,
  deny /sys/** rwklx,
}
