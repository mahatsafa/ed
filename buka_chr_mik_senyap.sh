#!/bin/sh
export DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
exec ~/.cache/ms-playwright/chromium-1255/chrome-linux64/chrome --remote-debugging-port=9222 --user-data-dir=$HOME/.engdis-chrome-profil --no-first-run --use-fake-device-for-media-stream --use-fake-ui-for-media-stream --use-file-for-fake-audio-capture=$HOME/.engdis-hening.wav https://ed.engdis.com/smktelkommlg
