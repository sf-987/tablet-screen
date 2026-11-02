# Security notes

What this setup exposes, to whom, and what runs with privileges. Read before installing.

## Threat model in one paragraph

A tablet connected by USB tethering is on a private two-node network with the laptop.
Everything here assumes that link is yours: the VNC servers have **no password and no
encryption**, because the only way to reach them is to be on that cable (or on the
laptop itself). If you ever expose them beyond the tether links, add a VNC password and
a tunnel; the script does not try to make unauthenticated VNC safe on a shared network.

## What listens, and who can connect

- `x11vnc`, one instance per tablet, TCP ports 5901, 5902 (configurable), **all
  interfaces**, but with `-allow 127.,<tether-subnet-1>.,<tether-subnet-2>.` computed at
  start time from the USB-tether interfaces present. Anything not from localhost or those
  /24s is refused at the TCP accept. The laptop's Wi-Fi/LAN address is never in the list
  unless you add `TABLET_ALLOW`.
- Consequence: the allow-list is a snapshot. If a tablet reconnects with a new address in
  a different /24 (Android re-randomises per session), run `tablet-screen on` again; the
  stale subnet is dropped, the new one added.
- `-nopw`: no VNC authentication. The control helper (below) also relies on this.

## What a connected VNC client can do

- **See** the tablet's region of your desktop, whatever is on it.
- **Not** move the mouse or type: servers run with `-input C` (clipboard only). With
  `TABLET_TOUCH=1` you grant mouse and keyboard to the tablet deliberately.
- **Send clipboard text to the laptop**, which x11vnc may place in the X selection
  (standard VNC behaviour; `-input` without `C` disables it, but the control channel
  needs it, see next point).
- **Issue x11vnc remote-control commands.** Servers run with `-remote_prefix TS_`, so a
  client sending clipboard text starting with `TS_` has x11vnc's `-R` command set:
  change cursor display, refresh, change scaling, disconnect other clients, change the
  allow list, stop the server. This is how `tablet-cursor-watch` hides and shows the
  cursor, and it is the one capability that goes beyond "viewing". It cannot run shell
  commands or move the pointer (input is still gated by `-input C`), but a hostile device
  on a tether cable could disrupt the servers or widen `-allow`. If that matters to you,
  set `TABLET_CURSOR=none`-equivalent by not running the watcher (`chmod -x
  tablet-cursor-watch`), remove `-remote_prefix` from `start_vnc`, and live with the
  stray cursor at the tablet's edge.
- Replies to those commands (`TS_ans=…`) are broadcast as clipboard text to **all**
  clients of that server, so a tablet's clipboard may contain such strings. Harmless.

## What runs as root

- `evdi-virtual-heads` (`sudo`): writes to `/sys/kernel/debug/dri/*/DVI-*/{force,edid_override}`
  and loads the `evdi` module; then runs `xrandr --setprovideroutputsource` **as your user**
  (it drops to `$SUDO_USER` with your `DISPLAY`/`XAUTHORITY`). It reads one file,
  `/usr/lib/firmware/edid/tablet.edid`, owned by root. No network, no user input parsed
  beyond `up|down|status`.
- `evdi-load.service`: `modprobe evdi` at boot, after the GPU driver, before the display
  manager. The module itself is DisplayLink's open-source `evdi`, built by you via DKMS
  from a tagged upstream release; nothing in this repo ships a binary module.
- `lightdm-ghost-heads` (optional, dummy plugs only): run by LightDM as root before the
  greeter; runs `xrandr --off` on the named heads. Edit the names before installing.
- `setup-usb-tether` (`sudo`): creates/updates one NetworkManager profile and offers to
  delete auto-generated profiles for USB interfaces that are not the default route. It
  prints the plan and asks before changing anything.
- `install.sh`: copies files to `/usr/local/{bin,sbin}`, `/etc/X11/xorg.conf.d`,
  `/etc/modprobe.d`, `/etc/systemd/system`, `/usr/lib/firmware/edid`; lists them and asks first.
- `tablet-screen` and `tablet-cursor-watch` run as **you**, no privileges.

## Network side effects

- The `usb-tether` profile sets `never-default`: the laptop will not route its internet
  through the tablet's cellular/Wi-Fi even though Android offers to. Without this, with
  a tethered tablet plugged in, all laptop traffic silently goes through the tablet.
- The pattern in `match.interface-name` must not match a USB-attached dock NIC you rely
  on, or that NIC loses its default route. `setup-usb-tether` excludes whatever currently
  carries the default route and prints the patterns it chose.

## Things this does not do

- No encryption of the VNC stream. On a USB cable the stream is not observable by third
  parties; on anything shared, it is.
- No authentication of the tablet. The cable is the credential.
- No integrity checking of the evdi source: `git checkout v1.15.1` is a tag, not a
  signature. Verify upstream yourself if that is part of your threat model.
