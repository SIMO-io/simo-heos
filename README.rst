=================================
Denon HEOS integration for SIMO.io
=================================

Local‑first HEOS control on a SIMO.io hub. This app adds a ``DENON HEOS``
gateway and an Audio Player controller so you can discover HEOS‑enabled
players, browse and play your HEOS Playlists and TuneIn stations, control
playback and volume, and trigger alert sounds — from the SIMO.io app and
Django Admin.

What you get (at a glance)
--------------------------

* Gateway type: ``DENON HEOS`` (auto‑created with defaults after restart).
* Component type: ``Audio player`` using the HEOS controller ("HEOS Player").
* Automatic discovery of HEOS devices and their local players.
* Optional HEOS account sign‑in per player component to expose library
  items (HEOS Playlists, TuneIn stations) directly in the app.
* Playback controls: play, pause, stop, next, previous, seek, volume,
  shuffle, loop.
* Optional alert playback: snapshot current state, play a sound, restore.
* LAN‑only transport: HEOS telnet (TCP 1255) and Denon AVR telnet (TCP 23).

Requirements
------------

* SIMO.io core ``>= 2.7.6`` (installed on your hub).
* Python ``>= 3.8``.
* Network reachability between the hub and your HEOS devices:
  - SSDP discovery: UDP multicast ``239.255.255.250:1900``.
  - HEOS control: TCP ``1255`` to each device.
  - Denon AVR control (for volume/source/zone): TCP ``23``.
* For alerts/streams: HEOS device must reach the hub’s HTTP server over
  LAN (the hub’s IP reachable from the device).

Install on a SIMO.io hub
------------------------

1. SSH to your hub and activate the hub’s Python environment
   (for example ``workon simo-hub``).

   .. code-block:: bash

      # On the hub
      workon simo-hub   # or activate your hub venv

2. Install the package.

   .. code-block:: bash

      pip install simo-heos

3. Enable the app in Django settings (``/etc/SIMO/settings.py``).

   .. code-block:: python

      # /etc/SIMO/settings.py
      from simo.settings import *  # keep platform defaults

      INSTALLED_APPS += [
          'simo_heos',
      ]

4. Apply migrations from this app.

   .. code-block:: bash

      cd /etc/SIMO/hub
      python manage.py migrate

5. Restart SIMO services so the new app and gateway type load.

   .. code-block:: bash

      supervisorctl restart all

After restart: discovery and logs
---------------------------------

Discovery runs continuously. After installation and restart, give the
hub a short time to find devices and populate players. In Django Admin,
you will see a ``DENON HEOS`` gateway created automatically with default
settings — open it to watch live logs of commands and state updates.

Add a HEOS audio player component
---------------------------------

Once players are discovered:

1. In the SIMO.io app: Components → Add New → Component.
2. Select Gateway: ``DENON HEOS``.
3. Select Component type: ``Audio player``.
4. Complete the form:
   - ``HEOS Player``: pick a discovered player.
   - Optional ``HEOS account username`` and ``password`` to enable access
     to your Playlists and Favorites (used per device; credentials are
     applied to the underlying HEOS device for browsing).
   - Usual component fields (name, room, etc.).
5. Save. The component’s alive/state will reflect the device.

Using it in the SIMO.io app
---------------------------

The Audio Player widget exposes playback and state:

* Play / Pause / Stop; Next / Previous.
* Seek position (seconds), if the current item supports it.
* Volume 0–99 at the device; the UI shows 0–100 and the gateway maps it.
* Shuffle and Loop/Repeat toggles.
* Library: HEOS Playlists and TuneIn stations discovered for that player.

Advanced controls (automations / scripts)
-----------------------------------------

From SIMO.io Python scripts or Admin tools, the controller supports:

* ``play_library_item(id, volume=None, fade_in=None)`` — play a Playlist
  or Station by id (see the component’s ``meta['library']``).
* ``play_uri(uri, volume=None)`` — play an HTTP/stream URL immediately.
* ``set_volume(0..100)``, ``set_shuffle_play(True/False)``,
  ``set_loop_play(True/False)``, ``seek(seconds)``.
* Alerts: use the SIMO “Audio Alert” component to play a one‑shot sound;
  the gateway snapshots current state, plays, then restores.
* Denon zones (advanced): ``zm(True|False)`` toggles the main zone,
  ``z2(True|False)`` toggles Zone 2.

Notes on discovery and device scope
-----------------------------------

* Each HEOS device exposes one or more player ids. This integration
  intentionally controls players on their own device IP only (no cross‑
  device control through another unit) for reliability.
* If a player dropdown is empty, wait for discovery or verify SSDP and
  TCP reachability to the device.
* Library items show as ``playlist-<cid>`` or ``station-<mid>`` ids.

Django Admin
------------

* A ``DENON HEOS`` gateway is created automatically after restart. Open it
  to view live logs of device I/O and discovery.
* Audio Player components (base type ``audio-player``) reflect live state
  and metadata (title, image, position, duration, volume, shuffle, loop,
  library). The component form exposes the HEOS credentials and player.

Troubleshooting
---------------

* No players show up:
  - Ensure services were restarted after installation.
  - Confirm SSDP multicast reaches the hub and that the hub can connect to
    TCP 1255 (HEOS) and TCP 23 (Denon AVR) on the device.
  - Wait for the next discovery cycle (runs every ~60 s).
* Library is empty or missing items: Provide valid HEOS account
  credentials in the component and allow a refresh cycle.
* Alerts don’t play or resume oddly: Ensure the device can reach the hub’s
  HTTP server; also verify the AVR can switch to the network input.
* Volume jumps: AVR volume uses 0–99; repeated set commands stabilize
  volume on some models during stream start.

Upgrade
-------

.. code-block:: bash

   workon simo-hub
   pip install --upgrade simo-heos
   python manage.py migrate
   supervisorctl restart all


License
-------

© Copyright by SIMO LT, UAB. Lithuania.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see `<https://www.gnu.org/licenses/>`_.
