# Design notes: why it's built this way

This documents the reasoning and the dead ends, because the dead ends are where the
time goes. Written October 2026 against Fedora 44 Cinnamon (X11), NVIDIA 2070 Super
with the proprietary driver, two Samsung S-family tablets.

## The problem is not the streaming

Sending pixels to a tablet and getting touch back is solved (VNC, Sunshine/Moonlight,
Weylus, Deskreen all do it). The hard part is making the laptop **believe it has another
monitor**, because:

- On X11, outputs belong to the GPU's display driver. RandR lets you *configure*
  outputs, not *create* them. Only the driver can add one, and each driver has its 
  crazy opinion about how that should work -- or typically, not work.
- On Wayland, each compositor has its own private virtual-output mechanism (Mutter and
  KWin via the screencast portal, wlroots via a headless backend). No shared protocol.
  Gnome has a sort-of solution, but it seems very fragile as a Miracast clone that 
  crashes regularly.
- Tablets are DisplayPort *sources* over USB-C, not sinks, and there is no standard USB
  "display class", so a tablet can never be a monitor at the cable level. It has to be a
  network client. Apple (Sidecar) and Samsung/Microsoft (Second Screen = a Miracast sink
  built into Windows) make this invisible by owning both ends. Linux owns neither.

So every Linux solution is: *fake an output somehow*, then stream it. This repo's
contribution is mostly the first half.

## Getting an output: what was tried, in order

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

### HDMI dummy plugs (what this repo uses)

A $3 plug with an EDID chip makes the connector *physically* connected. The driver treats
it exactly like a monitor, docked or undocked, with no config. Downsides: it occupies a
connector, costs a CRTC, advertises 16:9 modes (letterbox on a 16:10 tablet), and the
GPU drives it at boot so the login screen can land on it (fix in `lightdm/`, or plug in
after login). A USB-C-to-HDMI hub gives you a second connector and keeps other USB-C or 
USB-A ports free for the tablets' cables or other devices.

### evdi (DisplayLink's virtual display driver) — the principled alternative

[evdi](https://github.com/DisplayLink/evdi) is an out-of-tree DRM module that creates a
GPU-less card with virtual connectors. A connector becomes "connected" when a userspace
client attaches to it with an EDID (that's what DisplayLink's daemon does; `pyevdi` in
the evdi repo lets you write your own in ~50 lines, feeding it
`tools/tablet-1920x1200.edid`). X auto-adds the card as a second GPU under `modesetting`;
after `xrandr --setprovideroutputsource modesetting NVIDIA-0` its outputs appear in
`xrandr` like any monitor (reverse PRIME; the NVIDIA driver renders and copies). Then
everything downstream of this repo is unchanged.

Advantages over dummy plugs: no hardware, no connector used, its own CRTCs (not the
GPU's four), an EDID in exactly the tablet's shape, and nothing exists at boot so no
greeter problem. Disadvantages: it's an out-of-tree kernel module that must rebuild on
every kernel update (Fedora: `akmod-evdi` via the displaylink-rpm Copr), and reverse
PRIME on NVIDIA has version-dependent quirks (may need `nvidia-drm.modeset=1`). It is the
better design and the worse thing to depend on when you're on travel and in a hotel 
room with dubious connectivity. Not implemented here; the script needs only 
`TABLET_OUTPUTS` pointed at the evdi output names.

### Switching the BIOS to hybrid graphics

Would put the laptop panel on the Intel iGPU, whose driver accepts the `--addmode`
trick. Also moves every external port's display path through reverse PRIME, changes
the whole layout, and may expose no spare Intel connector anyway. For any modern display,
this is also going to drive *every pixel* through both GPUs, and that's a lot of 
bandwidth, power, and can cause side effects to other things you might want to run.
Too big a change for this purpose; worth it only if you want hybrid mode for battery 
life regardless.

## Scaling: the one global UI scale

X11 desktops scale all monitors by the same factor. A 4K 15" laptop panel wants 200%; a
tablet region at 1440x900 under 200% shows a quarter of the content. Attempts to give the
*panel* a smaller resolution instead, so the desktop could run at 100%:

- `xrandr --scale 0.5x0.5` on the panel works at the X level but the desktop's layout
  model still thinks the panel is 3840 wide, places neighbours accordingly, and leaves a
  pointer-blocking gap. Also, combining a transform with other changes in one xrandr
  call produced `BadMatch (RRSetScreenSize)` on NVIDIA which doesn't want to play nice
  with anything like 'let someone smart take over this' and tends to treat it more like 
  'I know better than you, I'll just refuse anything you ask for regardless of whether I
  say it should work.'
- Modelines in a `Monitor` section bound via `Option "Monitor-DP-3"` *in the Screen
  section* (NVIDIA reads it there, not in `Device`), with `ModeValidation` tokens to
  pass the panel's sync-range check: the modes appear in RandR, but they are driven as
  raw rasters to the eDP panel, which only accepts its native timing --> voila, instant
  black screen.
- `FlatPanelProperties "Scaling = Native"` makes the driver generate GPU-scaled modes
  (`ViewPortIn = 1920x1080, ViewPortOut = 3840x2160`), and explicit `MetaModes` with
  `ViewPortIn` work too — but NVIDIA exposes those only through RandR 1.1 screen sizes
  (`xrandr -s`) and nvidia-settings. The RandR 1.2 per-output mode list that every
  desktop's Display settings reads contains only validated raster modes, i.e. native
  only. **There is no config that makes a scaled laptop-panel mode selectable in
  Display settings on the NVIDIA driver.**

The Winning Answer: let the panel have its 200%, run the tablet heads at 3840x2160 so 
they carry 1080p-worth of content at 2x, and have x11vnc downsample the region by half
(`-scale 1/2:nb`) so the wire and the tablet still see 1920x1080. Costs x11vnc four times
the pixels to poll; acceptable on a modern CPU. When the panel is off (docked), run 100%
and the tablets at 1440x900 unscaled.

## Layout: who owns it

Every desktop has a settings daemon that saves the monitor layout per *set of connected
outputs* and re-applies it on login and whenever that set appears. An early version of
this script positioned the heads with xrandr and re-applied when the daemon moved them.
Two parties re-applying conflicting layouts every two seconds crashed Cinnamon, and other
things in the Fedora environment, repeatedly, and left overlapping outputs (two outputs 
showing the same framebuffer region looks like a tablet mirroring a slice of the panel). 
Ultimately, that involved a lot of rebooting to debug. The settled rule: the script never
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
  clipboard text from VNC *clients* into remote control. That is what the script uses:
  a 40-line VNC client connects to each server's own port, sends `TS_cmd=…` as
  ClientCutText, and reads the `TS_ans=…` reply. Clients run with `-input C`
  (clipboard only) so this works while the tablets remain input-less.
- `-wireframe`, window-move copyrect and `-scrollcopyrect` (RECORD extension) crashed
  x11vnc 0.9.17 (`caught signal: 11`) during a window drag across clipped servers. They
  are bandwidth optimisations irrelevant on a cable; `-nowf -nowcr -noscr`.
- The 5 ms `-wait/-defer` and `-noxdamage` noticeably cut latency under a compositing
  WM; XDamage reporting through Muffin was unreliable.

## Why USB tethering and not Wi-Fi

- Hotel and conference Wi-Fi isolate clients; the tablet can't reach the laptop at all.
- A laptop-hosted hotspot while also a Wi-Fi client (AP+STA) is supported by Intel AX
  cards in principle but must share the channel with the hotel AP and drops when it
  roams. Same for Miracast/Wi-Fi Direct, which is why Samsung Second Screen is flaky
  anywhere but at home.
- An extra USB Wi-Fi dongle as a dedicated AP: the one tested (an AICsemi AIC8800 "WiFi
  6" stick, sold under many names) has no mainline driver and a vendor driver that breaks
  on kernel updates. Realtek 88x2bu-class sticks are the same story. If you must have a
  dongle, pick a MediaTek MT7612U/MT7921AU (`mt76`, in-kernel, AP mode works), or carry
  a travel router.
- All of these wifi / wireless directions are a security nightmare, and driving the
  tablets the way we do will turn it into a major bandwidth hog. Everyone around you 
  will be annoyed, and you're likely to drop pixels regularly because most hotel or
  conference setups don't provide the kind of bandwidth this wants for low-latency and
  high-resolution tablets as monitors.
- USB tethering gives a private point-to-point link per tablet, the lowest latency of
  any option, charges the tablet, needs no password on the VNC servers (which are also
  bound to those subnets only), and works on every network or none.

## Why VNC and not Sunshine/Moonlight

VNC sends lossless pixels of changed regions: text is razor sharp, an idle tablet costs
nothing, no pairing, any viewer. It falls over on full-screen motion. Sunshine sends a
GPU-encoded H.264/HEVC stream at a fixed frame rate: smooth motion, ~30 ms latency,
slightly softened text, pairing and a port range per tablet, one instance per captured
monitor. For mail, calendar, terminals and logs VNC is the better fit; for a web-session
tablet Sunshine probably wins. The head and the layout are identical either way, so
Sunshine can replace x11vnc for one tablet later without touching anything else.

## Wayland

None of this applies. The compositor owns outputs and input; there is no `-clip`-able
root framebuffer and no xrandr. Use what the compositor offers: GNOME's
`gnome-network-displays` (Miracast or Chromecast to the tablet; creates a virtual monitor
via Mutter), KDE's equivalent through the screencast portal, or for wlroots compositors a
headless output plus `wayvnc`. Those are the right tools and this repo is the X11
holdout's version.
