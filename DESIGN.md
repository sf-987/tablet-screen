# Design notes: why it's built this way

This documents the reasoning and the dead ends, because the dead ends are where the
time goes. Written October 2026 against Fedora 44 Cinnamon (X11), kernel 7.2, NVIDIA
2070 Super with the proprietary 595 driver, two Samsung tablets. The setup went through
three generations: xorg.conf tricks (failed), HDMI dummy plugs (works, zero software),
evdi virtual heads (works, zero hardware; the current default).

## The problem is not the streaming

Sending pixels to a tablet and getting touch back is solved (VNC, Sunshine/Moonlight,
Weylus, Deskreen all do it). The hard part is making the laptop **believe it has another
monitor**, because:

- On X11, outputs belong to the GPU's display driver. RandR lets you *configure*
  outputs, not *create* them. Only the driver can add one, and each driver has its own
  crazy idea about how that should work.
- On Wayland, each compositor has its own private virtual-output mechanism (Mutter and
  KWin via the screencast portal, wlroots via a headless backend). No shared protocol.
- Tablets are DisplayPort *sources* over USB-C, not sinks, and there is no standard USB
  "display class", so a tablet can never be a monitor at the cable level. It has to be a
  network client. Apple (Sidecar) and Samsung/Microsoft (Second Screen = a Miracast sink
  built into Windows) make this invisible by owning both ends. Linux owns neither.

So every Linux solution is: *fake an output somehow*, then stream it. This repo's
contribution is mostly the first half.

## Getting an output

Here's a brief history of what was tried, in order, and the results achieved.

### `xrandr --addmode` on a disconnected connector (VirtScreen's way)

[VirtScreen](https://github.com/kbumsik/VirtScreen) (2018) relied on the old Intel DDX
driver exposing a `VIRTUAL1` output. The modern `modesetting`, `amdgpu` and `i915`
drivers don't have it, but they do let you add a mode to a *disconnected physical*
connector and enable it:

```bash
xrandr --newmode "1920x1200_60" $(cvt 1920 1200 60 | sed -n 's/^Modeline *"[^"]*" *//p')
xrandr --addmode HDMI-A-1 1920x1200_60
xrandr --output HDMI-A-1 --mode 1920x1200_60 --right-of eDP-1
```

If the driver refuses to light a connector it considers disconnected, the kernel
parameter `video=HDMI-A-1:1920x1200@60e` ("e" = pretend connected) fixes that.
**On the open drivers this is the whole answer and no hardware is needed.**

The NVIDIA proprietary driver rejects `RRAddOutputMode` on a disconnected head with
`BadMatch`, always, and ignores `video=` (it isn't a KMS driver in that sense). Hence
everything below.

### NVIDIA `ConnectedMonitor` + `CustomEDID` (xorg.conf)

NVIDIA's documented way to run a headless output: tell the driver a head is connected
and hand it an EDID. It works (the fake heads came up and were accepted) but
`ConnectedMonitor` **replaces** detection rather than adding to it, so listing only the
fake heads blacked out every real monitor, including the text consoles, and needed a
single-user-mode recovery. Listing the real heads too would work but hard-codes the
docked/undocked monitor sets into a file read at X start, and MST names (`DP-0.1`) aren't
reliable there. Rejected as too fragile for a travel machine. If you go this way, stage a
`systemd-run --on-active=4m` that deletes the file unless you cancel it.

### HDMI dummy plugs (the zero-software fallback)

A $3 plug with an EDID chip makes the connector *physically* connected. The driver treats
it exactly like a monitor, docked or undocked, with no config. Downsides: it occupies a
connector, costs a CRTC, advertises 16:9 modes (letterbox on a 16:10 tablet), and the
GPU drives it at boot so the login screen can land on it (fix in `lightdm/`, or plug in
after login). A USB-C-to-HDMI hub gives you a second connector and keeps USB-A free for
the tablets' cables.

### evdi (DisplayLink's virtual display driver) — what this repo now uses by default

[evdi](https://github.com/DisplayLink/evdi) is an out-of-tree DRM module that creates
GPU-less cards with virtual connectors. Three findings made it practical:

- **No userspace client is needed.** A connector normally becomes "connected" only when a
  client attaches with an EDID (DisplayLink's daemon, or libevdi/pyevdi). The kernel's
  debugfs does the same thing: `echo on > /sys/kernel/debug/dri/N/DVI-I-1/force` and
  `cat tablet.edid > .../edid_override`. That's all `evdi/evdi-virtual-heads` does.
- **NVIDIA as PRIME output source works unassisted.** With one `OutputClass` snippet
  binding `modesetting` to evdi devices, X adds the cards as GPU screens at startup;
  `xrandr --listproviders` shows them as `Sink Output` providers, and
  `xrandr --setprovideroutputsource modesetting NVIDIA-0` makes NVIDIA render into them.
  No `BusID`, no `Inactive` device sections. (Driver 595, Xorg 21, kernel 7.2.)
- **The module must load late.** Put `evdi` in `/etc/modules-load.d/` and dracut copies
  it into the initramfs; evdi then becomes DRM card0 and the LUKS prompt and console are
  drawn on a display that doesn't exist. A systemd unit ordered after
  `systemd-modules-load` and before `display-manager` avoids that.

Compared with dummy plugs: no hardware, no connector used, no CRTC used, no greeter
problem, an EDID exactly the tablet's shape and refresh. Cost: the zero-copy PRIME path is
refused (`evdi_gem_mmap: Don't allow imported objects to be mapped`), so every damaged
frame is copied into the virtual framebuffer by the X server on the CPU — 20–50 % of a
core during a large window drag, nothing when static. A 30 Hz EDID halves it; VNC can't
use 60 fps anyway. And it's a DKMS module that must rebuild on each kernel update (it
built cleanly against 7.2; keep `dkms status` in the pre-trip checklist).

### Switching the BIOS to hybrid graphics

Would put the laptop panel on the Intel iGPU, whose driver accepts the `--addmode`
trick. Also moves every external port's display path through reverse PRIME, changes
the whole layout, and may expose no spare Intel connector anyway. Too big a change for
this purpose; worth it only if you want hybrid mode for battery life regardless. This
will activate copying pixels between the discrete and integrated graphics buffers,
and that's a lot of bandwidth, latency, and power - not something to be ignored in
any real-world use case.

## Scaling: the one global UI scale

X11 desktops scale all monitors by the same factor. A 4K 15" laptop panel wants 200%; a
tablet region at 1440x900 under 200% shows a quarter of the content. Attempts to give the
*panel* a smaller resolution instead, so the desktop could run at 100%:

- `xrandr --scale 0.5x0.5` on the panel works at the X level but the desktop's layout
  model still thinks the panel is 3840 wide, places neighbours accordingly, and leaves a
  pointer-blocking gap. Also, combining a transform with other changes in one xrandr
  call produced `BadMatch (RRSetScreenSize)` on NVIDIA.
- Modelines in a `Monitor` section bound via `Option "Monitor-DP-3"` *in the Screen
  section* (NVIDIA reads it there, not in `Device`), with `ModeValidation` tokens to
  pass the panel's sync-range check: the modes appear in RandR, but they are driven as
  raw rasters to the eDP panel, which only accepts its native timing → black screen.
- `FlatPanelProperties "Scaling = Native"` makes the driver generate GPU-scaled modes
  (`ViewPortIn = 1920x1080, ViewPortOut = 3840x2160`), and explicit `MetaModes` with
  `ViewPortIn` work too — but NVIDIA exposes those only through RandR 1.1 screen sizes
  (`xrandr -s`) and nvidia-settings. The RandR 1.2 per-output mode list that every
  desktop's Display settings reads contains only validated raster modes, i.e. native
  only. **There is no config that makes a scaled laptop-panel mode selectable in
  Display settings on the NVIDIA driver.**

Resolution: let the panel have its 200%, run the tablet heads at 3840x2160 so they carry
1080p-worth of content at 2x, and have x11vnc downsample the region by half
(`-scale 1/2:nb`) so the wire and the tablet still see 1920x1080. Costs x11vnc four times
the pixels to poll; acceptable on a modern CPU. When the panel is off (docked), run 100%
and the tablets at 1440x900 unscaled.

## Layout: who owns it

Every desktop has a settings daemon that saves the monitor layout per *set of connected
outputs* and re-applies it on login and whenever that set appears. An early version of
this script positioned the heads with xrandr and re-applied when the daemon moved them.
Two parties re-applying conflicting layouts every two seconds crashed Cinnamon,
repeatedly, and left overlapping outputs (two outputs showing the same framebuffer region
looks like a tablet mirroring a slice of the panel). The settled rule: the script never
positions anything beyond the initial `--right-of` when it enables a head; the user
arranges once in Display settings and Applies; the script clips whatever geometry results.

## x11vnc specifics that cost time

- `-ncache` extends the framebuffer with a cache region; viewers that don't understand
  it (RealVNC, AVNC) show the desktop as a small box above a tall black strip.
- `-multiptr` creates a second XInput master keyboard; GTK4/Qt/Electron apps lose
  keyboard focus until it goes away. Not needed; one pointer is fine for a monitor.
- With `-clip`, x11vnc clamps the reported/painted cursor into the clip region while the
  pointer is elsewhere, so a stray cursor sits at the tablet's edge. Fixed by telling the
  server `noshow_cursor` / `show_cursor` as the pointer leaves/enters the region.
- `-R` remote control is one X property that whichever server reads first consumes
  (and clears), so it can't target one of two servers, and a second write before the
  read overwrites the first. `-remote_prefix` is *not* a fix for that: it routes
  clipboard text from VNC *clients* into remote control. That is what the repo uses:
  `tablet-cursor-watch` keeps one VNC connection open to each server's own port, sends
  `TS_cmd=show_cursor` / `noshow_cursor` / `refresh` as ClientCutText the moment the
  pointer crosses a head's edge, and reconnects if a server restarts. Servers run with
  `-input C` (clipboard only) so this works while the tablets remain input-less. A
  first version forked a fresh handshake per event and took 1–2 s per crossing; the
  persistent version takes ~100–200 ms, dominated by the 100 ms pointer poll.
- Restarting servers too quickly fails with `could not obtain listening port`: x11vnc
  exits gracefully on SIGTERM and holds the port for a moment. `tablet-screen` waits for
  the old processes to go before starting new ones.
- `-scale 1/2:nb` (nearest neighbour) shreds the painted cursor's one-pixel outline;
  blended `-scale 1/2` is clean and costs some CPU per changed region.
- `-wireframe`, window-move copyrect and `-scrollcopyrect` (RECORD extension) crashed
  x11vnc 0.9.17 (`caught signal: 11`) during a window drag across clipped servers. They
  are bandwidth optimisations irrelevant on a cable; `-nowf -nowcr -noscr`.
- The 5 ms `-wait/-defer` and `-noxdamage` noticeably cut latency under a compositing
  WM; XDamage reporting through Muffin was unreliable.

## Why USB tethering and not Wi-Fi

- Sometimes the Hotel and conference Wi-Fi networks isolate clients; the tablet can't 
  reach the laptop at all in those environments.
- A laptop-hosted hotspot while also a Wi-Fi client (AP+STA) is supported by Intel AX
  cards in principle but must share the channel with the hotel AP and drops when it
  roams. Same for Miracast/Wi-Fi Direct, which is why Samsung Second Screen is flaky
  anywhere but at home.
- An extra USB Wi-Fi dongle as a dedicated AP: the one tested (an AICsemi AIC8800 "WiFi
  6" stick, sold under many names) has no mainline driver and a vendor driver that breaks
  on kernel updates. Realtek 88x2bu-class sticks are the same story. If you must have a
  dongle, pick a MediaTek MT7612U/MT7921AU (`mt76`, in-kernel, AP mode works), or carry
  a travel router.
- USB tethering gives a private point-to-point link per tablet, the lowest latency of
  any option, charges the tablet, needs no password on the VNC servers (which are also
  bound to those subnets only), and works on every network or none. The caveat is that
  you'll enable USB tethering, which contains some inherent security risks unless you
  set it up correctly.
- NetworkManager details that bit: the tablet advertises a default gateway (set
  `ipv4.never-default`); a profile is active on one device at a time unless
  `connection.multi-connect multiple`; per-port auto-generated profiles lose their
  settings when a tablet moves to another port, so use one `match.interface-name`
  catch-all. The tablet never exposes its name over the cable (USB descriptors carry only
  `SAMSUNG_Android` and the serial), so the serial is the identity.

## Why VNC and not Sunshine/Moonlight

VNC sends lossless pixels of changed regions: text is razor sharp, an idle tablet costs
nothing, no pairing, any viewer. It falls over on full-screen motion. Sunshine sends a
GPU-encoded H.264/HEVC stream at a fixed frame rate: smooth motion, ~30 ms latency,
slightly softened text, pairing and a port range per tablet, one instance per captured
monitor. For mail, calendar, terminals and logs VNC is the better fit; for a web-session
content of videos, games, and so forth, tablets using the Sunshine configuration probably 
wins. The head and the layout are identical either way, so Sunshine can replace x11vnc
for one tablet later without touching anything else.

## Wayland

None of this applies. The compositor owns outputs and input; there is no `-clip`-able
root framebuffer and no xrandr. Use what the compositor offers: GNOME's
`gnome-network-displays` (Miracast or Chromecast to the tablet; creates a virtual monitor
via Mutter), KDE's equivalent through the screencast portal, or for wlroots compositors a
headless output plus `wayvnc`. Those are the right tools and this repo is the X11
holdout's version.
