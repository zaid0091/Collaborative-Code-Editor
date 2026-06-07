#include <tunables/global>

profile executor-sandbox flags=(attach_disconnected) {
  #include <abstractions/base>

  deny /proc/*/mem rw,
  deny /proc/*/environ r,
  deny /proc/*/maps r,
  /proc/self/status r,
  /proc/self/stat r,

  deny /sys/** rw,

  deny network,

  /tmp/** rw,
  /run/** rw,
  /usr/** r,
  /lib/** r,
  /sandbox/** r,
}
