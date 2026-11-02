# evdi mode: virtual heads without dummy plugs

[evdi](https://github.com/DisplayLink/evdi) is DisplayLink's out-of-tree DRM driver. It
creates GPU-less "cards" with virtual connectors. We force each connector "connected"
with a tablet-shaped EDID from the kernel's debugfs (no userspace daemon), X adopts the
cards as `modesetting` GPU screens, and the real GPU renders into them as a PRIME output
source. The result is ordinary outputs (`DVI-I-1-1`, `DVI-I-2-2`) that the desktop treats
like monitors and that `tablet-screen` serves over VNC.

Verified: Fedora 44, kernel 7.2, Xorg 21, NVIDIA 595 proprietary (RTX 2070 Super),
Cinnamon 6.6. Should work with any GPU driver that can be a PRIME source (all the open
ones can).

## Files

| file | install to | purpose |
|---|---|---|
| `evdi-virtual-heads` | `/usr/local/sbin/` | `up`/`down`/`status`: force connectors with the EDID, attach the provider |
| `20-evdi.conf` | `/etc/X11/xorg.conf.d/` | bind `modesetting` (no accel) to evdi devices; matches only evdi |
| `evdi.conf` | `/etc/modprobe.d/` | `initial_device_count=2` (one card per tablet) |
| `evdi-load.service` | `/etc/systemd/system/` | load the module late (see **initramfs trap**) |
| `tablet-3840x2400-30hz.edid` | `/usr/lib/firmware/edid/tablet.edid` | the virtual monitor's identity (default) |
| `tablet-3840x2400-60hz.edid` | — | same at 60 Hz, if you want it |

## Install

```bash
# 1. the module, via DKMS so it rebuilds on kernel updates
sudo dnf install dkms kernel-devel-$(uname -r) gcc make git libdrm-devel
git clone https://github.com/DisplayLink/evdi.git && cd evdi && git checkout v1.15.1
sudo make -C module install_dkms
dkms status                                   # evdi/1.15.1, <kernel>: installed

# 2. configs
sudo install -m755 evdi-virtual-heads /usr/local/sbin/
sudo install -m644 20-evdi.conf       /etc/X11/xorg.conf.d/
sudo install -m644 evdi.conf          /etc/modprobe.d/evdi.conf
sudo install -m644 evdi-load.service  /etc/systemd/system/
sudo install -D -m644 tablet-3840x2400-30hz.edid /usr/lib/firmware/edid/tablet.edid
sudo systemctl enable evdi-load.service
sudo reboot
```

Secure Boot: DKMS generates a self-signed MOK at `/var/lib/dkms/mok.pub`. If
`mokutil --sb-state` says enabled, enrol it once (`sudo mokutil --import
/var/lib/dkms/mok.pub`, reboot, Enroll MOK in the blue menu) or the module will be refused.

## Use

```bash
xrandr --listproviders               # NVIDIA-0 (Source Output) + two 'modesetting' Sink Output providers
sudo evdi-virtual-heads up           # forces the connectors; prints the DVI-I-* outputs
```

Then in `~/.config/tablet-screen.conf`:

```bash
TABLET_OUTPUTS="DVI-I-1-1 DVI-I-2-2"   # names from xrandr; evdi heads report a real size, so no auto-detect
TABLET_MODE=3840x2400
TABLET_VNC_SCALE=1/2
```

and `tablet-screen on 2`, arrange once in Display settings, Apply, `tablet-screen on 2`.
`sudo evdi-virtual-heads down` unforces the connectors (outputs disappear). A one-line
sudoers rule for `/usr/local/sbin/evdi-virtual-heads` makes `up`/`down` passwordless.

## The initramfs trap

Do not put `evdi` in `/etc/modules-load.d/`. dracut copies those files into the
initramfs, so evdi loads before the GPU driver and becomes DRM card0; the console and the
LUKS passphrase prompt are then drawn on a display that doesn't exist (black screen,
typing the passphrase blind may not work). Recovery: at GRUB press `e`, append
`module_blacklist=evdi` to the `linux` line, boot, remove the file, `sudo dracut -f`.
`evdi-load.service` loads the module after the GPU and before the display manager instead.

## Why 30 Hz

The virtual head's pixels get from the GPU into the evdi framebuffer by a CPU copy in the
X server (the zero-copy path is refused: `evdi_gem_mmap: Don't allow imported objects to
be mapped` in dmesg is normal). Cost is proportional to damaged area × refresh. VNC can't
deliver 60 fps anyway, so a 30 Hz EDID halves the copy work at no visible cost. Expect
Xorg at ~10 % idle (x11vnc polling), 20–50 % of a core while dragging a large window
across a tablet, ~0 % when the tablet shows a static screen. Dummy plugs avoid this
entirely because the GPU drives them directly; that's the trade for needing no hardware.

Other EDIDs: `python3 ../tools/make_edid.py W H --hz N -o /usr/lib/firmware/edid/tablet.edid`,
then `down` / `up`.

## Expected dmesg lines (harmless)

- `evdi_painter_connect: Edid length too small` at X startup: X probed the connector
  before `up` provided an EDID.
- `evdi_gem_mmap: Don't allow imported objects to be mapped: owner: nvidia_drm`: PRIME
  buffer import refused, CPU copy used instead (see above).
