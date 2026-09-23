# Urbit pier for Omarchy

A bar-widget plugin that installs Vere and supervises **one** local Urbit ship: a fake `~zod`, a mined comet, a moon/planet/star from a `.key` file, or an existing pier directory.

This is the local runtime. Direct messages still live in `ahlmark.urbit-dms`, which can keep talking to a hosted Tlon ship.

```
◌            ← dim when stopped, full color when live
┌──────────────────────────────────┐
│ ~zod                    [switch] │
│ Compiling Arvo           Fake    │
│ Open Landscape                   │
│ http://127.0.0.1:8080            │
└──────────────────────────────────┘
```

Left-click toggles the panel. Middle- or right-click refreshes. `t` starts/stops, `l` opens Landscape, `r` refreshes, arrows/`j`/`k` move, Enter activates.

The ship is a **systemd user unit** (`urbit-pier.service`), not a child of the bar. Reloading the Omarchy shell will not kill it. The unit is not enabled at login; you start it from the switch.

## Install

From git (what Omart friends run):

```bash
omarchy plugin add https://github.com/ahlmark/urbit-pier.git --enable
```

From this folder:

```bash
chmod +x urbit-pier.py
omarchy plugin validate .
mkdir -p ~/.config/omarchy/plugins
cp -a . ~/.config/omarchy/plugins/ahlmark.urbit
rm -rf ~/.config/omarchy/plugins/ahlmark.urbit/.git
omarchy plugin validate ~/.config/omarchy/plugins/ahlmark.urbit
omarchy plugin enable ahlmark.urbit --section right --before ahlmark.urbit-dms
```

If `omarchy plugin enable` does not place it, open **Setup → Bar** and drop **Urbit** onto the right section.

## First run

1. Click **Install Vere**. That downloads the live `linux-x86_64` binary from `bootstrap.urbit.org` into `~/.local/share/urbit/urbit`.
2. Click **Create fake ~zod** (or mine a comet / boot a keyfile / attach a pier).
3. Flip the switch. First boot of a fake `~zod` can take several minutes and wants about 2GB of RAM (this machine has swap). The chip pulses until Landscape answers on `http://127.0.0.1:8080`.

HTTP is port **8080**, so Vere does not need root to bind port 80.

## Config

`~/.config/omarchy/urbit.json` (mode `600`), created on first successful command:

```json
{
  "binary": "~/.local/share/urbit/urbit",
  "piersDir": "~/urbit",
  "httpPort": 8080,
  "loom": 31,
  "active": "zod",
  "piers": [
    { "id": "zod", "kind": "fake", "ship": "zod", "path": "~/urbit/zod" }
  ]
}
```

Kinds: `fake`, `comet`, `real`, `attached`. Keyfile **contents** are never stored; a `real` pier may remember the key **path** until the first boot finishes.

Sanity-check the helper:

```bash
python3 ./urbit-pier.py status
```

## What this version does not do

- Attach a Dojo TTY (the ship runs with `-t` under systemd)
- Pack / meld / chop
- Auto-start at login
- Run two ships at once
- Point `ahlmark.urbit-dms` at localhost automatically
- Forward Ames through NAT

## Publish on Omart

Omart listing ids are Hoon `term`s, so they cannot contain dots. The Omarchy plugin id stays `ahlmark.urbit`; the bazaar id is `ahlmark-urbit`.

Open Landscape → Omart → **Publish** and paste:

| field | value |
| --- | --- |
| id | `ahlmark-urbit` |
| name | `Urbit` |
| git | `https://github.com/ahlmark/urbit-pier.git` |
| author | `Ahlmark` |
| version | `0.1.0` |
| description | `Boot a fake ~zod or manage a local Urbit pier from the Omarchy bar. Installs Vere, then starts and stops one ship as a systemd user unit.` |
| tags | `urbit, bar, pier, vere` |
| kinds | `bar-widget` |

Or from the dojo on the publisher comet:

```
:omart +omart/publish %ahlmark-urbit 'Urbit' 'https://github.com/ahlmark/urbit-pier.git' 'Boot a fake ~zod or manage a local Urbit pier from the Omarchy bar. Installs Vere, then starts and stops one ship as a systemd user unit.'
```

The generator hardcodes version `0.1.0` and author `you`. Use the Publish page if you want author `Ahlmark` and tags.

Friends install with:

```
omarchy plugin add https://github.com/ahlmark/urbit-pier.git --enable
```

## Files

| file | role |
| --- | --- |
| `manifest.json` | plugin id `ahlmark.urbit`, bar-widget on the right |
| `Panel.qml` | chip + dropdown |
| `Service.qml` | QML wrapper around the helper |
| `Model.js` | JSON parsing and labels |
| `urbit-pier.py` | Vere download, pier registry, systemd unit |
