#!/usr/bin/env bash
# install.sh — install tablet-screen and, optionally, the evdi virtual-head support.
#
#   ./install.sh            scripts + example config only (dummy-plug mode needs nothing else)
#   ./install.sh --evdi     also install the evdi configs and systemd unit (module via DKMS
#                           is a separate step, see evdi/README.md)
#   ./install.sh --lightdm  also install the LightDM pre-greeter fix for dummy plugs
#
# Everything this touches is listed before anything is written; nothing runs as root
# until you confirm. See SECURITY.md for what each piece does and why it needs root.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

EVDI=0; LIGHTDM=0
for a in "$@"; do case $a in --evdi) EVDI=1;; --lightdm) LIGHTDM=1;; *) echo "unknown option $a"; exit 1;; esac; done

user_files=(
  "tablet-screen            -> /usr/local/bin/tablet-screen"
  "tablet-cursor-watch      -> /usr/local/bin/tablet-cursor-watch"
  "tools/setup-usb-tether   -> /usr/local/bin/setup-usb-tether"
)
root_files=()
(( EVDI )) && root_files+=(
  "evdi/evdi-virtual-heads  -> /usr/local/sbin/evdi-virtual-heads"
  "evdi/20-evdi.conf        -> /etc/X11/xorg.conf.d/20-evdi.conf"
  "evdi/evdi.conf           -> /etc/modprobe.d/evdi.conf"
  "evdi/evdi-load.service   -> /etc/systemd/system/evdi-load.service (enabled)"
  "evdi/tablet-3840x2400-30hz.edid -> /usr/lib/firmware/edid/tablet.edid"
)
(( LIGHTDM )) && root_files+=(
  "lightdm/lightdm-ghost-heads -> /usr/local/sbin/lightdm-ghost-heads (edit head names first!)"
  "lightdm/50-ghost-heads.conf -> /etc/lightdm/lightdm.conf.d/50-ghost-heads.conf"
)

echo "Will install (as root):"
printf '  %s\n' "${user_files[@]}" "${root_files[@]}"
conf="${XDG_CONFIG_HOME:-$HOME/.config}/tablet-screen.conf"
[[ -e $conf ]] || echo "  tablet-screen.conf.example -> $conf (as you)"
echo
read -r -p "Proceed? [y/N] " a; [[ $a == [yY] ]] || exit 0

sudo install -m755 tablet-screen tablet-cursor-watch /usr/local/bin/
sudo install -m755 tools/setup-usb-tether /usr/local/bin/
[[ -e $conf ]] || install -m644 tablet-screen.conf.example "$conf"

if (( EVDI )); then
  sudo install -m755 evdi/evdi-virtual-heads /usr/local/sbin/
  sudo install -m644 evdi/20-evdi.conf /etc/X11/xorg.conf.d/20-evdi.conf
  sudo install -m644 evdi/evdi.conf /etc/modprobe.d/evdi.conf
  sudo install -m644 evdi/evdi-load.service /etc/systemd/system/evdi-load.service
  sudo install -D -m644 evdi/tablet-3840x2400-30hz.edid /usr/lib/firmware/edid/tablet.edid
  sudo systemctl daemon-reload && sudo systemctl enable evdi-load.service
  if [[ -e /etc/modules-load.d/evdi.conf ]]; then
    echo "WARNING: /etc/modules-load.d/evdi.conf exists; it will pull evdi into the initramfs"
    echo "         (black screen before login). Remove it and run: sudo dracut -f"
  fi
  if ! dkms status 2>/dev/null | grep -q '^evdi.*installed'; then
    echo "NOTE: evdi module not installed via DKMS yet; see evdi/README.md step 1, then reboot."
  fi
fi

if (( LIGHTDM )); then
  sudo install -m755 lightdm/lightdm-ghost-heads /usr/local/sbin/
  sudo install -m644 lightdm/50-ghost-heads.conf /etc/lightdm/lightdm.conf.d/
fi

echo
echo "Installed. Next:"
echo "  1. edit $conf"
echo "  2. setup-usb-tether            (once; creates the NetworkManager profile)"
(( EVDI )) && echo "  3. reboot, then: sudo evdi-virtual-heads up"
echo "  then: tablet-screen on 2"
