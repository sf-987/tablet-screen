# tablet-screen

Use one or two tablets (Android, iPad, anything with a VNC viewer) as extra monitors for
a Linux laptop running **X11**, over a **USB cable**, with no Wi-Fi involved. In theory
this will scale to N tablets connected concurrently.  You become limited by the maximum
Xorg resolution and what number of connections your graphics card (ghost plugs) and/or
CPU (evdi) can handle for load, while still leaving your laptop usable.  Two tablets on
an older Intel 8-core 16-thread laptop seems fine.

This process works via a simple bash script around launching one or more sessions of 
`x11vnc`, a small script to help make the Xorg cursor more visible and behave sanely, 
and two ways of giving the GPU an extra head to drive: (a virtual one via [evdi](evdi/), 
or a $3 HDMI dummy plug). There is also a write-up of everything that *doesn't* work 
and why ([DESIGN.md](DESIGN.md)).

**Status:** works for on Fedora 44 Cinnamon (X11 session), ThinkPad T15g,
RTX 2070 Super (NVIDIA proprietary 595), kernel 7.2, Samsung Galaxy Tab S9 Ultra + S8
Ultra, October 2026. X11 only. This is not a product or a heavily supported solution,
it's one that works unlike others that have gone into bit-rot and is being posted to
help other people be productive. Think of it as a working starting point that is coded
to be as simple and automated as possible - but was only developed on one platform. 
See [Scope](#scope).

```
tablet-screen on        # enable a virtual tablet head and a VNC server
tablet-screen on 2      # enable two tablet heads, one VNC server each
tablet-screen off       # turn off all the virtual heads
tablet-screen status    # provide some useful info about the current setup
```

---

## How it works

```
 extra GPU head (evdi virtual or dummy plug)  ─►  region of the X framebuffer  ─►  x11vnc -clip  ─►  USB tether  ─►  VNC viewer
```

1. The GPU needs an output to drive. Either **evdi** creates a virtual one (no hardware;
   see [`evdi/`](evdi/)), or a **dummy plug** (an HDMI "headless ghost" with an EDID chip)
   makes a spare connector look occupied. The desktop then treats it like any monitor: you
   arrange it next to your laptop screen in Display settings.
2. `x11vnc -clip` serves exactly that monitor's rectangle, one server per tablet.
3. Each tablet is on **USB tethering** (a private point-to-point link over the cable); the
   viewer connects to the laptop's address on that link. No Wi-Fi, no pairing.
4. `tablet-cursor-watch` shows a tablet's cursor only while the mouse is on that tablet.

## Requirements

- Linux, **X11 session** (`echo $XDG_SESSION_TYPE` → `x11`). Wayland: see DESIGN.md.
- `x11vnc`, `xrandr`, `xdotool`, `python3`, `ip` (iproute2), `udevadm`.
  Fedora: `sudo dnf install x11vnc xdotool`. Debian/Ubuntu: `sudo apt install x11vnc xdotool`.
- An extra head per tablet: **evdi** ([`evdi/README.md`](evdi/README.md)), or a dummy plug
  per spare connector (4K HDMI dummy plugs come in cheap multi-packs; their EDIDs list
  1920x1080 and other modes too; the author's were
  [these](https://www.amazon.com/dp/B0GS4X87T5)).
- A USB cable per tablet; a tablet that can USB-tether (all Android; iPad needs a hotspot
  plan, or fall back to a laptop-hosted Wi-Fi hotspot).
- A VNC viewer on the tablet. Tested: RealVNC Viewer and AVNC (Android).

## Install

```bash
./install.sh            # scripts + example config (dummy-plug mode needs nothing else)
./install.sh --evdi     # also the evdi configs and systemd unit (module via DKMS: evdi/README.md)
```

It lists every file it will write and asks before using `sudo`. [SECURITY.md](SECURITY.md)
describes what listens, what a connected tablet can do, and what runs as root.

Then set up the heads: [`evdi/README.md`](evdi/README.md) (recommended), or plug in dummy
plugs (nothing to install; the script auto-detects them).

## First-time setup

### 1. Find the heads

```bash
xrandr | grep 'connected'
tablet-screen heads
```

Dummy plugs show up as connected outputs reporting `0mm x 0mm` and are auto-detected.
evdi heads (`DVI-I-1-1`, `DVI-I-2-2`) report a size, so list them in the config:
`TABLET_OUTPUTS="DVI-I-1-1 DVI-I-2-2"`.

CRTC budget (dummy plugs only): every active GPU output needs a CRTC and consumer GPUs
have 4–6 (`xrandr --listproviders` shows `crtcs:`). Docked with two monitors plus the
panel, a 4-CRTC GPU has room for one plug. evdi heads have their own CRTCs.

### 2. Arrange the heads in Display settings (not with xrandr)

Every desktop's settings daemon (Cinnamon `csd-xrandr`, GNOME `gsd-xrandr`, KDE
`kscreen`, XFCE `xfsettingsd`) saves a layout per *set of connected monitors* and
re-applies it whenever that set appears. Scripts that position outputs with xrandr fight
it and lose, sometimes taking the desktop down. So, once per situation (docked, undocked):

1. `tablet-screen on 2`: enables the heads (to the right of everything, the first time).
2. Display settings: drag the tablet heads to where the tablets physically sit, set
   rotation for a portrait tablet, set resolution and UI scale per [Scaling](#scaling).
   **Apply**, **Keep**.
3. `tablet-screen on 2` again: the servers don't follow live moves, so re-run after any
   rearrangement (a tablet showing a slice of the wrong screen means you forgot).

### 3. Connect the tablets by USB

On each tablet: cable in, Settings → Connections → Mobile Hotspot and Tethering → **USB
tethering**. On the laptop, once, with at least one tablet tethered:

```bash
setup-usb-tether
```

It creates a single NetworkManager profile, `usb-tether`, for USB network interfaces that
never takes the default route (Android advertises a gateway; without this the laptop's
internet silently goes through the tablet), can be active on several cables at once, and
outranks the auto-generated "Wired connection N" profiles, which it offers to delete. It
derives the interface patterns from the USB interfaces present and leaves whatever
carries the default route (e.g. a dock's USB Ethernet) alone; it prints the plan and asks.
The equivalent by hand is one `nmcli con add` with `match.interface-name`,
`ipv4/ipv6.never-default yes`, `connection.multi-connect multiple` and
`connection.autoconnect-priority 100`. Check afterwards: `ip route | head -1` (default
via Wi-Fi/Ethernet) and `nmcli con show --active` (`usb-tether` once per cable).

Note: serial numbers of tablets can be found on the tablet, via Settings -> About Tablet,
where the S/N should be listed directly.  Compare that to what you see in the scripts.

`tablet-screen on 2` prints what to type into each viewer:

```
  tablet 1 -> port 5901  (3840x2400+0+0)  connect the viewer to:
      10.174.63.54:5901  (USB tether on enp44s0u1, serial R52X...)
      10.167.170.148:5901  (USB tether on enp0s20f0u2u2, serial R52T7...)
```

The **port** chooses which head the tablet shows; the **address** must be the one on
that tablet's own cable (the other is simply refused). Android tethering picks a new
random 10.x range per session, so the address changes; the USB serial doesn't, and
`TABLET_NAMES="<serial>=S9U <serial>=S8U"` in the config labels the lines. In the viewer,
turn on **view-only** so touching the tablet doesn't move your mouse and the viewer's own
touch cursor goes away.

The servers accept connections only from localhost and the USB-tether subnets; they are
invisible to whatever Wi-Fi or LAN the laptop is on. For a test over your home LAN add
`TABLET_ALLOW="192.168.1."`.

## Scaling

X11 desktops have **one UI scale for all monitors**, and on the NVIDIA driver no scaled
resolution for the laptop panel can be made selectable (DESIGN.md explains the attempts).
So the panel's needs win and the tablets adapt:

| Desktop UI scale | Head mode | `TABLET_VNC_SCALE` | Tablet receives |
|---|---|---|---|
| 200 % (4K laptop panel) | 3840x2400 (evdi) or 3840x2160 (plug) | `1/2` | 1080p/1200p-worth of content at 1920 wide |
| 100 % (panel off, or 1080p/1440p panel) | 1440x900 / 1920x1080 | `1` | that resolution 1:1 |

Set the head's mode in Display settings to match; `TABLET_MODE` only applies the first
time the script enables a head. The evdi EDID is 16:10 like most tablets; a dummy plug
is 16:9, which gives a thin letterbox nobody notices.

## Settings

`~/.config/tablet-screen.conf` is a shell fragment; same-named environment variables
override it. See `tablet-screen.conf.example`.

```bash
TABLET_OUTPUTS="DVI-I-1-1 DVI-I-2-2"   # heads in tablet order (default: auto-detect 0mm x 0mm outputs)
TABLET_MODE=3840x2400          # mode set when the script first enables a head
TABLET_VNC_SCALE=1/2           # x11vnc -scale; 1 = none; "1/2:nb" = no blending (faster, ragged cursor)
TABLET_WAIT=20                 # x11vnc poll interval ms (5 = snappier, more CPU)
TABLET_XDAMAGE=0               # 1 = poll only damaged regions (near-zero idle CPU; may lag under some compositors)
TABLET_TOUCH=0                 # 1 = allow mouse/keyboard input from the tablets
TABLET_CURSOR=paint            # paint: x11vnc draws the cursor (any viewer); shape: viewer draws it (AVNC yes, RealVNC no)
TABLET_NAMES="R52X...=S9U R52T...=S8U"   # USB serial -> label
TABLET_ALLOW=                  # extra allowed client prefixes, e.g. 192.168.1.
TABLET_BASE_PORT=5900          # tablet N listens on BASE_PORT+N
```

## Performance expectations

VNC sends lossless pixels of what changed. Text, terminals, logs, mail: crisp and quick.
Video, smooth scrolling, dragging a big window across a tablet: laggy, some tearing. With
evdi heads the X server also copies each changed frame into the virtual framebuffer on the
CPU, so expect Xorg ~10 % idle, 20–50 % of a core during a large drag (dummy plugs: ~0 %
extra). For a motion-heavy tablet the upgrade is
[Sunshine](https://github.com/LizardByte/Sunshine) + Moonlight (GPU-encoded video, ~30 ms)
on the same head; not integrated here.

## Login screen on a dummy-plug head (plugs only)

With plugs permanently attached the GPU enables them at boot and the display manager's
greeter may land on one. Plug them in after logging in, or install the LightDM
pre-greeter script in [`lightdm/`](lightdm/) (edit the head names at its top first):

```bash
sudo install -m755 lightdm/lightdm-ghost-heads /usr/local/sbin/
sudo install -m644 lightdm/50-ghost-heads.conf /etc/lightdm/lightdm.conf.d/
```

evdi heads don't exist until `evdi-virtual-heads up`, so they never have this problem.

## Troubleshooting

- **Viewer shows a tiny desktop with black below**: an x11vnc started with `-ncache`;
  this script never does that.
- **Mouse jumps to the tablet when you touch it**: viewer not in view-only, or `TABLET_TOUCH=1`.
- **Keyboard dies in some apps while a tablet is connected**: never use x11vnc `-multiptr`.
- **Tablet shows a slice of another screen / both tablets show the same thing**: heads
  moved or overlapping; arrange in Display settings, Apply, `tablet-screen on 2`.
- **`could not obtain listening port` in a head's log**: an old server was still exiting;
  the script now waits, but `tablet-screen off; pkill -9 x11vnc; tablet-screen on 2` clears it.
- **`caught signal: 11`**: x11vnc segfault. The known trigger (window-move copy-rect with
  `-clip`) is disabled; if it recurs, `coredumpctl info x11vnc`.
- **Stray cursor stuck at a tablet's edge**: `tablet-cursor-watch` isn't running
  (`$XDG_RUNTIME_DIR/tablet-screen/cursor-watch.log`); needs `xdotool` and `python3`.
- **Black screen at boot after installing evdi**: the initramfs trap; see `evdi/README.md`.
- Logs: `$XDG_RUNTIME_DIR/tablet-screen/<head>.log`.

## Scope

- **X11 only.** On Wayland the compositor owns virtual outputs; use `gnome-network-displays`
  (GNOME), KDE's screencast-based virtual monitor, or a wlroots headless output + `wayvnc`.
- Tested on Cinnamon; uses only xrandr/x11vnc, so MATE, XFCE, KDE-X11, GNOME-X11 should
  work unchanged.
- The NVIDIA-specific parts (why plugs or evdi are needed at all) are in DESIGN.md; on the
  open drivers a disconnected connector can be enabled with `xrandr --addmode` and no
  hardware or evdi is needed.
- Not maintained as a project. Fork freely. MIT.

## Files

- `tablet-screen`, `tablet-cursor-watch`: the script and its cursor helper.
- `install.sh`, `tools/setup-usb-tether`: installer and the NetworkManager setup; both print a plan and ask.
- `SECURITY.md`: what listens, what a tablet can do, what runs as root.
- `evdi/`: virtual heads without hardware (helper, X and module configs, systemd unit, EDIDs).
- `lightdm/`: optional pre-greeter fix for dummy plugs.
- `tools/make_edid.py`: generates a CVT-RB EDID of any size/refresh (used for the evdi EDIDs;
  also for programmable dummy plugs).
- `DESIGN.md`: why it's built this way, what was tried, caveats for non-NVIDIA GPUs and Wayland.
