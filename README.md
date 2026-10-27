# tablet-screen

Use one or two tablets (Android, iPad, anything with a VNC viewer) as extra monitors
for a Linux laptop running **X11**, over a **USB cable**, with no Wi-Fi involved.
This can be trivially extended to more monitors, until you run out of GPU-hardware
limitations on the number of screens it allows.

It is a 300-line bash script centered around the `x11vnc` tool, plus notes on the 
one hardware trick that makes it work on the NVIDIA proprietary driver (a $3 HDMI
dummy plug), and a write-up of everything that *doesn't* work and why 
([DESIGN.md](DESIGN.md)).

**Status:** works for the author on Fedora 44 Cinnamon (X11 session), ThinkPad T15g,
RTX 2070 Super (proprietary driver), Samsung Galaxy Tab S9 Ultra + S8 Ultra, as of
October 2026. X11 only. Not a product; a starting point. See [Scope](#scope).

```
tablet-screen on        # enable extra screens for android tablet(s) (any should work)
tablet-screen off       # turns off all tablet screens enabled
tablet-screen status    # provide some details on how things are working
```

---

## How it works

```
 laptop GPU head (dummy plug)  ──►  region of the X framebuffer  ──►  x11vnc -clip  ──►  USB tether  ──►  VNC viewer on tablet
```

1. The GPU needs a *real* extra output to drive. A spare physical connector with a
   **dummy plug** (an HDMI/DP "headless ghost" with an EDID chip inside) makes the driver
   believe a monitor is attached. The desktop then treats it like any monitor: you
   arrange it next to your laptop screen in Display settings.
2. `x11vnc -clip` serves exactly that monitor's rectangle, one server per tablet, as a
   normal VNC desktop.
3. The tablet is connected by **USB tethering** (the tablet shares "its network" over the
   cable; the laptop gets a private point-to-point link). Any VNC viewer on the tablet
   connects to the laptop's address on that link. No Wi-Fi, no hotel network, nothing
   to pair.
4. A small watcher hides the cursor on a tablet while the mouse is elsewhere, so you
   don't see a stray cursor pinned to the tablet's edge (an artefact of `-clip`).

If you are on the open-source GPU drivers (Intel, AMD, nouveau) you may not need the
dummy plug at all; see [DESIGN.md → "Without dummy plugs"](DESIGN.md#without-dummy-plugs).

## Requirements

- Linux, **X11 session** (check: `echo $XDG_SESSION_TYPE` → `x11`). Wayland: see DESIGN.md.
- `x11vnc`, `xrandr`, `xdotool` (cursor hiding), `python3` (cursor control), `ip` (iproute2).
  Fedora: `sudo dnf install x11vnc xdotool`. Debian/Ubuntu: `sudo apt install x11vnc xdotool`.
- One spare display connector per tablet (HDMI, DP, USB-C with DP alt mode, a USB-C hub
  with HDMI…) and a dummy plug for each. 4K dummy plugs are sold in cheap multi-packs and
  are fine; their EDIDs list 1920x1080 and other smaller modes too.
  The author used a 4-pack of 4K HDMI dummy plugs from Amazon
  ([B0GS4X87T5](https://www.amazon.com/dp/B0GS4X87T5)); any "HDMI dummy plug / headless
  display emulator" that lists 1920x1080@60 works.
- A USB cable per tablet and a tablet that can **USB-tether** (all Android tablets can;
  iPads can with a hotspot plan, or fall back to a laptop-hosted Wi-Fi hotspot).
- A VNC viewer on the tablet. Tested: RealVNC Viewer (Android), AVNC (Android, F-Droid).
  Configure it for "view-only" mode to make the extra (and annoying) cursor go away.

## Install

```bash
sudo install -m755 tablet-screen /usr/local/bin/
```

Optional settings file, `~/.config/tablet-screen.conf` (see [Settings](#settings)).

## First-time setup

### 1. Plug in the dummy plugs and find the heads

Do not boot with the dummy plugs installed, it tends to make your login screen
move to a non-existant monitor.  It can also play havoc with your screen resolutions.
And most fun of all, there is an upper limit on the total X,Y resolution you can
have, so depending on your panel, other desktop / dock monitors, etc., you can 
get some truly weird behavior.  Just plug them in after you have logged into your
desktop.  I use one on an HDMI port and one on an Anker USB-C hub with an HDMI
port on the hub so I can drive two tablets while on travel.

```bash
xrandr | grep ' connected'
```

Each dummy plug shows up as a `connected` output reporting `0mm x 0mm` physical size
(real monitors report their size). The script auto-detects those. If auto-detection
picks up something else, set `TABLET_OUTPUTS="HDMI-0 DP-1"` in the config file.

Watch the **CRTC budget**: every active output needs a CRTC and consumer GPUs have 4–6
(`xrandr --listproviders` shows `crtcs: N`). Docked with two monitors and the laptop panel,
a 4-CRTC GPU has room for one tablet; undocked, for two or three.

### 2. Arrange the heads in your desktop's Display settings

This is the step that must be done in the desktop, **not** with xrandr. Every desktop's
settings daemon (Cinnamon's `csd-xrandr`, GNOME's `gsd-xrandr`, KDE's `kscreen`, XFCE's
`xfsettingsd`) saves a layout per *set of connected monitors* and re-applies it whenever
that set appears. Scripts that position outputs with xrandr fight that daemon and lose,
sometimes taking the whole desktop (networking, etc.) down with them. Skip the corruption
and reboots, just don't go there.

So, for each situation you use (docked, undocked):

1. `tablet-screen on` — enables the heads (they land to the right of everything the
   first time) and starts the servers.
2. Open Display settings. Drag the tablet heads where the tablets physically are
   (left and right of the laptop, say). Set rotation if a tablet stands in portrait.
   Set the resolution and UI scale per [Scaling](#scaling). **Apply**, then **Keep**.
3. `tablet-screen on` again — restarts the servers on the new rectangles. (The servers
   don't follow live moves; re-run `on` after any rearrangement of the desktop and
   monitor placement. Annoying, but this is the simplest and quickest fix for the 
   loss of tracking and the strange tablet displays you will have if you skip this 
   step.)

From then on `tablet-screen on` brings the heads up where you left them.

### 3. Connect the tablets by USB

On the tablet: plug in the cable, Settings --> Connections --> Mobile Hotspot and 
Tethering --> **USB tethering** turn on. On the laptop a new interface appears:

```bash
ip -br addr           # e.g. enp0s20f0u5  10.174.63.67/24 <-- the laptop's address on that link
nmcli -t -f NAME,DEVICE con show --active
sudo nmcli con mod "Wired connection 5" con-name tether-tab1 \
     ipv4.never-default yes ipv6.never-default yes connection.autoconnect yes # <-- use the name you saw, which may differ from "Wired connection 5"
sudo nmcli con up tether-tab1
```

You'll effectively repeat this for each tablet, and change the name "tether-tab1" to 
"tether-tabN" as you go along.  The flag `never-default` stops the laptop from routing 
its internet through the tablet - which is very recommended for security reasons, unless
you want other people at the hotel, conference, Starbucks, or whatever to enjoy your 
tablet's screen content. Do this once per tablet (the profile is remembered per cable/port).

`tablet-screen on` prints, for each tablet, the address:port to type into the viewer:

```
  tablet 1 -> port 5901  (3840x2160+0+270)  connect the viewer to:
      10.174.63.67:5901  (USB tether)
```

Each tablet can only reach the address on its own cable; if one address refuses, use the
other. In the viewer, turn on **view-only** (RealVNC: in the connection's settings; AVNC:
toggle in the toolbar) so touching the tablet doesn't move your mouse.

The servers accept connections **only** from localhost and the USB-tether subnets. They
are invisible to whatever Wi-Fi or LAN the laptop is on. For testing over your home LAN,
add `TABLET_ALLOW="192.168.1."` to the config.

## Scaling

X11 desktops have **one UI scale for all monitors**. There is no per-monitor scaling and,
on the NVIDIA driver, no way to give the laptop panel a selectable scaled resolution
(details in DESIGN.md). So the panel's needs win and the tablets adapt:

| Your desktop UI scale | Tablet head mode | `TABLET_VNC_SCALE` | What the tablet shows |
|---|---|---|---|
| 200% (typical 4K laptop panel) | 3840x2160 (default) | `1/2` (default) | 1080p-worth of content, sent as 1920x1080 |
| 100% (1080p/1440p panel, or docked with panel off) | 1440x900 or 1920x1080 | `1` | that resolution, 1:1 |

Set the head's mode in Display settings to match (the script's `TABLET_MODE` is only used
the first time it enables a head). A 16:10 tablet showing a 16:9 region gets a thin
letterbox; nobody notices.

## Settings

`~/.config/tablet-screen.conf` is a shell fragment; environment variables of the same
names override it.

```bash
TABLET_OUTPUTS="HDMI-0 DP-1"   # heads in tablet order (default: auto-detect 0mm x 0mm outputs)
TABLET_MODE=3840x2160          # mode set when the script enables a head
TABLET_VNC_SCALE=1/2           # x11vnc output scale; 1 = none
TABLET_TOUCH=0                 # 1 = allow mouse/keyboard input from the tablets
TABLET_CURSOR=paint            # paint: x11vnc draws the cursor (any viewer); shape: viewer draws it (AVNC yes, RealVNC Android no)
TABLET_ALLOW=                  # extra client address prefixes, e.g. 192.168.1.
TABLET_BASE_PORT=5900          # tablet N listens on BASE_PORT+N
TABLET_WAIT=5                  # x11vnc poll interval (ms); raise to 10–20 if CPU-bound
```

## Login screen on a tablet head (optional fix)

With dummy plugs permanently attached, the GPU enables them at boot and the display
manager's greeter may land on one, i.e. on a screen you can't see. Options: plug the
dummies in after logging in (simplest), or install the LightDM pre-greeter script in
[`lightdm/`](lightdm/), which turns the heads off before the greeter draws:

```bash
sudo install -m755 lightdm/lightdm-ghost-heads /usr/local/sbin/
sudo install -m644 lightdm/50-ghost-heads.conf /etc/lightdm/lightdm.conf.d/
```

Edit the head names at the top of the script first. GDM/SDDM have equivalent hooks.
If you get it wrong, just boot without the dummy plugs installed - it's easy, it's
painless, and it always works.

## Troubleshooting

- **Viewer shows a tiny desktop with black below** — an x11vnc `-ncache` server; this
  script never uses it, so you're running a different x11vnc.
- **Mouse jumps to the tablet when you touch it** — viewer not in view-only, or
  `TABLET_TOUCH=1`.
- **Keyboard stops working in some apps while a tablet is connected** — don't use
  x11vnc's `-multiptr` (this script doesn't); MPX second keyboards confuse GTK4/Qt.
- **A tablet shows a slice of the laptop screen** — you moved the heads after starting
  the servers. Re-run the command `tablet-screen on` again.
- **Both tablets show the same thing** — the two heads overlap in the layout. 
  Re-arrange, Apply, re-run.
- **`caught signal: 11` in `$XDG_RUNTIME_DIR/tablet-screen/*.log`** — x11vnc segfault.
  This script disables the known culprits (`-nowf -nowcr -noscr`); if it still happens,
  `coredumpctl info x11vnc`.
- **Lag** — VNC is fine for mail, documents, terminals and logs; it is not fine for video
  or smooth scrolling. For that, the same head can be streamed with
  [Sunshine](https://github.com/LizardByte/Sunshine) + Moonlight instead (GPU-encoded
  H.264, ~30 ms); not integrated here. Patches welcome.

## Scope

- **X11 only.** On Wayland the compositor owns virtual outputs and this whole approach
  doesn't apply: GNOME has `gnome-network-displays` (Miracast/Chromecast to the tablet,
  creates a virtual monitor), KDE has similar via its screencast portal, wlroots has a
  headless backend. See DESIGN.md.
- Tested on Cinnamon; should work unchanged on MATE, XFCE, KDE-X11, GNOME-X11 since it
  only uses xrandr and x11vnc.
- The author is not actively maintaining this as a project. Fork freely.

## Files

- `tablet-screen` — the script.
- `lightdm/` — optional pre-greeter fix for dummy plugs.
- `tools/make_edid.py`, `tools/tablet-1920x1200.edid` — generates a 16:10 EDID, for people
  who want to write a tablet-shaped EDID into a programmable dummy plug or feed a
  virtual-output driver (evdi). Not needed for the default setup.
- `DESIGN.md` — why it's built this way, what was tried, what to do without NVIDIA,
  without dummy plugs, without X11.
