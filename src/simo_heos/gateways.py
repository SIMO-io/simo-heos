import sys, traceback, time, threading
from collections import OrderedDict
from simo.core.gateways import BaseObjectCommandsGatewayHandler
from simo.core.forms import BaseGatewayForm
from simo.core.middleware import drop_current_instance
from simo.core.models import Component
from simo.core.utils.helpers import get_self_ip
from .utils import discover_heos_devices
from .transport import HEOSDeviceTransporter
from .models import HeosDevice, HPlayer


class HEOSGatewayHandler(BaseObjectCommandsGatewayHandler):
    name = "DENON HEOS"
    config_form = BaseGatewayForm

    periodic_tasks = (
        ('discover_devices', 60),
        ('read_transport_buffers', 1)
    )
    states_map = {
        'stop': 'stopped', 'play': 'playing', 'pause': 'paused'
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transporters = {}
        self.player_transporters = {}
        self.player_interrupts = {}
        self.alert_stops = {}
        self.playing_alerts = {}

    def discover_devices(self):
        from .controllers import HeosPlayer
        active_players = []
        active_devices = []
        for d_info in discover_heos_devices():
            print(f"Analyze device: {d_info['uid']} - {d_info['name']}")
            if d_info['uid'] not in self.transporters \
            or self.transporters[d_info['uid']].ip != d_info['ip']:
                try:
                    self.transporters[d_info['uid']] = HEOSDeviceTransporter(
                        d_info['ip'], d_info['uid']
                    )
                except:
                    print(traceback.format_exc(), file=sys.stderr)
                    continue
            transporter = self.transporters[d_info['uid']]
            try:
                resp = transporter.cmd('heos://player/get_players')
            except:
                print(traceback.format_exc(), file=sys.stderr)
                self.transporters.pop(d_info['uid'])
                continue
            if not resp or resp.status != 'success':
                print(f"Bad respponse: {resp}")
                continue

            heos_device, new = HeosDevice.objects.update_or_create(
                uid=d_info['uid'], defaults={
                    'ip': d_info['ip'], 'name': d_info['name'],
                    'connected': True
                }
            )
            active_devices.append(heos_device.id)

            for player_info in resp.payload:
                # This is crazy! In fact it is possible to connect to
                # one of your HEOS enabled device and control all other
                # players via it.
                # It seems smart, but that's definitely not the most reliable
                # way of communication. We prefer keeping things separated
                # the way they naturally are.
                if player_info['ip'] != heos_device.ip:
                    continue
                player, new = HPlayer.objects.update_or_create(
                    device=heos_device, pid=player_info['pid'],
                    defaults={'name': player_info['name']}
                )
                self.player_transporters[player.id] = d_info['uid']
                active_players.append(player.id)
                for comp in Component.objects.filter(
                    controller_uid=HeosPlayer.uid, alive=False,
                    config__player=player.id
                ):
                    comp.alive = True
                    comp.save()
                self.update_now_playing_media(transporter, player.pid)

            for comp in Component.objects.filter(
                controller_uid=HeosPlayer.uid, alive=True
            ).exclude(config__player__in=active_players):
                comp.alive = False
                comp.save()

        HeosDevice.objects.all().exclude(
            id__in=active_devices
        ).update(connected=False)

        authorize_transports = {}
        for component in Component.objects.filter(
            controller_uid=HeosPlayer.uid, alive=True
        ):
            if not all([
                component.config.get('username'),
                component.config.get('password')]
            ):
                continue
            hplayer = HPlayer.objects.filter(
                id=component.config['hplayer']
            ).select_related('device').first()
            if not hplayer:
                continue
            if hplayer.device in authorize_transports:
                authorize_transports[
                    hplayer.device
                ]['players'].append(component)
            else:
                authorize_transports[hplayer.device] = {
                    'players': [component],
                    'un': component.config.get('username'),
                    'pw': component.config.get('password')
                }

        for device, credentials in authorize_transports.items():
            transport = self.transporters.get(device.uid)
            if not transport:
                continue
            resp = transport.cmd('heos://system/check_account')
            if not resp or resp.status != 'success':
                continue
            signed_in_user = resp.values.get('un')
            if signed_in_user == credentials['un']:
                print(f"{signed_in_user} is signed in on {device}.")
                for player in credentials['players']:
                    if player.error_msg and 'sign in' in player.error_msg.lower():
                        player.error_msg = None
                        player.save()
                    try:
                        self.update_library(transport, player)
                    except:
                        print(traceback.format_exc(), file=sys.stderr)
                        continue
                continue
            transport.authorize(credentials['un'], credentials['pw'])


    def update_library(self, transport, player):
        print(f"Update library of {player}")

        current_library = OrderedDict(
            {item['id']: item for item in player.meta.get('library', [])}
        )
        mentioned_ids = []

        # Playlists
        resp = transport.cmd(f'heos://browse/browse?sid=1025')
        if not resp:
            return
        for item in resp.payload:
            id = f"playlist-{item['cid']}"
            current_library[id] = item
            current_library[id]['id'] = id
            current_library[id]['title'] = item.get('name')
            mentioned_ids.append(id)

        # TuneIn stations
        resp = transport.cmd(f'heos://browse/browse?sid=1028')
        if not resp:
            return
        for item in resp.payload:
            id = f"station-{item['mid']}"
            current_library[id] = item
            current_library[id]['id'] = id
            current_library[id]['title'] = item.get('name')
            mentioned_ids.append(id)

        for id in current_library.keys():
            if id not in mentioned_ids:
                current_library.pop(id)

        player.refresh_from_db()
        player.meta['library'] = list(current_library.values())
        player.save()

    def prepare_for_play(self, transport):
        denon_source = 'SITV'
        denon_resp = transport.denon_cmd('SI?', True)
        if denon_resp:
            for r in denon_resp:
                if r.startswith('SI'):
                    denon_source = r
        if denon_source != 'SINET':
            transport.denon_cmd(f"MUON")
            time.sleep(0.5)
            transport.denon_cmd(f"SINET")
            time.sleep(0.5)
            transport.denon_cmd(f"MUOFF")
            time.sleep(0.5)

        return denon_source


    def perform_value_send(self, component, value):
        print(f"{component}: {value}!")

        hplayer = HPlayer.objects.select_related('device').get(
            id=component.config['hplayer']
        )
        transport = self.transporters[hplayer.device.uid]

        if value in ('play', 'pause', 'stop'):
            transport.cmd(
                f"heos://player/set_play_state?pid={hplayer.pid}&state={value}"
            )

        if 'next' in value:
            transport.cmd(f'heos://player/play_next?pid={hplayer.pid}')

        if 'previous' in value:
            transport.cmd(f'heos://player/play_previous?pid={hplayer.pid}')

        if 'set_volume' in value:
            volume = value['set_volume']
            if volume > 99:
                volume = 99
            transport.denon_cmd(f"MV{volume:02}")
            component.meta['volume'] = value['set_volume']
            component.save()

        if 'loop' in value:
            resp = transport.cmd(
                f'heos://player/get_play_mode?pid={hplayer.pid}'
            )
            if not resp or resp.status != 'success':
                return
            component.meta['shuffle'] = resp.values.get('shuffle') != 'off'
            component.meta['loop'] = resp.values.get('repeat') != 'off'
            resp = transport.cmd(
                f"heos://player/set_play_mode?pid={hplayer.pid}"
                f"&repeat={'on_all' if component.meta['loop'] else 'off'}"
                f"&shuffle={'on' if component.meta['shuffle'] else 'off'}"
            )
            if resp and resp.status == 'success':
                component.meta['loop'] = value['loop']
            component.save()

        if 'shuffle' in value:
            resp = transport.cmd(
                f'heos://player/get_play_mode?pid={hplayer.pid}'
            )
            if not resp or resp.status != 'success':
                return
            component.meta['shuffle'] = resp.values.get('shuffle') != 'off'
            component.meta['loop'] = resp.values.get('repeat') != 'off'
            resp = transport.cmd(
                f"heos://player/set_play_mode?pid={hplayer.pid}"
                f"&repeat={'on_all' if component.meta['loop'] else 'off'}"
                f"&shuffle={'on' if component.meta['shuffle'] else 'off'}"
            )
            if resp and resp.status == 'success':
                component.meta['shuffle'] = value['shuffle']
            component.save()

        if 'ZM' in value:
            if value['ZM']:
                transport.denon_cmd('ZMON')
            else:
                transport.denon_cmd('ZMOFF')
            component.meta['ZM'] = value['ZM']
            component.save()

        if 'Z2' in value:
            if value['Z2']:
                transport.denon_cmd('Z2ON')
            else:
                transport.denon_cmd('Z2OFF')
            component.meta['Z2'] = value['Z2']
            component.save()

        if 'play_uri' in value:
            self.prepare_for_play(transport)

            if 'volume' in value:
                volume = value['volume']
                if volume > 99:
                    volume = 99
                transport.denon_cmd(f"MV{volume:02}")
            transport.cmd(
                f"heos://browse/play_stream?pid="
                f"{hplayer.pid}&url={value['play_uri']}"
            )
            if not any(
                [component.config.get('ZM'), component.config.get('Z2')]
            ):
                transport.denon_cmd(f"ZMON")


        if 'play_from_library' in value:
            print("PLAY LIBRARY ITEM: ", value)
            for item in component.meta.get('library', []):
                if item['id'] == value['play_from_library']:
                    threading.Thread(
                        target=self.play_library_item, daemon=True, args=(
                            transport, hplayer.pid, component, item,
                            value['volume'], value['fade_in']
                        )
                    ).start()
                    break

        if 'alert' in value:
            if not value['alert']:
                return self.finish_alert(transport, hplayer.pid, stop=True)

            alert = Component.objects.filter(id=value['alert']).first()
            if not alert:
                return

            denon_source = 'SITV'
            denon_resp = transport.denon_cmd('SI?', True)
            if denon_resp:
                for r in denon_resp:
                    if r.startswith('SI'):
                        denon_source = r


            # save current state if nothing is saved
            if hplayer.pid not in self.player_interrupts:
                resp = transport.cmd(
                    f'heos://player/get_now_playing_media?pid={hplayer.pid}'
                )
                if resp and resp.status == 'success':
                    resp.payload.update({
                        'volume': component.meta['volume'],
                        'shuffle': component.meta['shuffle'],
                        'loop': component.meta['loop'],
                        'state': component.value,
                        'SI?': denon_source
                    })
                    self.player_interrupts[hplayer.pid] = resp.payload

            if component.value == 'playing':
                resp = transport.cmd(
                    f"heos://player/set_play_state?pid={hplayer.pid}&state=stop"
                )
                if not resp or resp.status != 'success':
                    return

            resp = transport.cmd(
                f"heos://player/set_play_mode?pid={hplayer.pid}"
                f"&repeat={'on_one' if alert.config.get('loop', False) else 'off'}"
                f"&shuffle={'on' if component.meta['shuffle'] else 'off'}"
            )
            if resp and resp.status == 'success':
                component.meta['loop'] = alert.config['loop']


            if denon_source != 'SINET':
                transport.denon_cmd(f"MUON")
                time.sleep(0.5)
                transport.denon_cmd(f"SINET")
                time.sleep(0.5)
                transport.denon_cmd(f"MUOFF")
                time.sleep(0.5)

            if not any([component.config.get('ZM'), component.config.get('Z2')]):
                transport.denon_cmd(f"ZMON")
                time.sleep(0.5)

            volume = alert.config['volume']
            if volume > 99:
                volume = 99
            print("SET VOLUME TO: ", f"MV{volume:02}")
            transport.denon_cmd(f"MV{volume:02}")
            component.meta['volume'] = alert.config['volume']

            url = f"http://{get_self_ip()}{alert.config['stream_url']}"
            #url = f"http://192.168.0.121:8000{alert.config['stream_url']}"
            print("PLAY URL: ", url)
            start = time.time()
            transport.cmd(
                f"heos://browse/play_stream?pid={hplayer.pid}&url={url}"
            )
            # stupid denons accepts volume only after stream starts playing
            # so we force volume change for 2 seconds 4 times!!!
            for i in range(4):
                transport.denon_cmd(f"MV{volume:02}")
                time.sleep(0.5)

            component.save()


            if f"{transport.uid}_{hplayer.pid}" in self.playing_alerts:
                self.playing_alerts[
                    f"{transport.uid}_{hplayer.pid}"
                ]['comp'].set(False)

            self.playing_alerts[f"{transport.uid}_{hplayer.pid}"] = {
                'comp': alert, 'start': start
            }
            alert.set(True)
            if not alert.config['loop']:
                # Alert should get finished by events stream
                # however it that fails, we do it with the timer +20s later
                # than estimated duration of a sound
                finish_timer = threading.Timer(
                    alert.config['duration'] + 20, self.finish_alert,
                    args=[transport, hplayer.pid]
                )
                finish_timer.start()
                self.playing_alerts[
                    f"{transport.uid}_{hplayer.pid}"
                ]['finish_timer'] = finish_timer

    def finish_alert(self, transport, h_pid, stop=False):
        if f"{transport.uid}_{h_pid}" not in self.playing_alerts:
            return
        if stop:
            transport.cmd(
                f"heos://player/set_play_state?pid={h_pid}&state=stop"
            )
        comp = self.playing_alerts[f"{transport.uid}_{h_pid}"]['comp']
        start = self.playing_alerts[f"{transport.uid}_{h_pid}"]['start']
        finish_timer = self.playing_alerts[
            f"{transport.uid}_{h_pid}"
        ].get('finish_timer')
        if not stop and time.time() - start < comp.config['duration']:
            # false trigger from events stream
            return
        if comp.config['loop'] and not stop:
            # false trigger from events stream
            return
        comp.set(False)
        if finish_timer:
            finish_timer.cancel()
        self.playing_alerts.pop(f"{transport.uid}_{h_pid}")

        transport.cmd(
            f"heos://player/remove_from_queue?pid={h_pid}&qid=1"
        )

        if h_pid in self.player_interrupts:

            transport.cmd(
                f"heos://player/set_volume?pid={h_pid}"
                f"&level={self.player_interrupts[h_pid]['volume']}"
            )
            loop = self.player_interrupts[h_pid]['loop']
            shuffle = self.player_interrupts[h_pid]['shuffle']
            transport.cmd(
                f"heos://player/set_play_mode?pid={h_pid}"
                f"&repeat={'on_all' if loop else 'off'}"
                f"&shuffle={'on' if shuffle else 'off'}"
            )
            volume = self.player_interrupts[h_pid]['volume']
            transport.denon_cmd(f"MV{volume:02}")
            time.sleep(1)
            if 'SI?' != 'SINET':
                transport.denon_cmd(self.player_interrupts[h_pid]['SI?'])
                time.sleep(0.5)
                transport.denon_cmd(self.player_interrupts[h_pid]['SI?'])
                time.sleep(0.5)
                # stupid denons sometimes doesn't accept volume change
                # after source change, so we force it 6 times in 3 seconds
                for i in range(6):
                    transport.denon_cmd(f"MV{volume:02}")
                    time.sleep(0.5)

            if self.player_interrupts[h_pid]['state'] == 'playing':
                print("RESUME PLAYING: ", self.player_interrupts)
                if self.player_interrupts[h_pid].get('sid') == 3:
                    mid = self.player_interrupts[h_pid].get('album_id', '0')
                    name = self.player_interrupts[h_pid].get('station', '-')
                    transport.cmd(
                        f"heos://browse/play_stream?pid={h_pid}&sid=3"
                        f"&cid=1&mid={mid}&name={name}"
                    )
                elif self.player_interrupts[h_pid].get('qid'):
                    qid = self.player_interrupts[h_pid].get('qid')
                    transport.cmd(
                        f"heos://player/play_queue?pid={h_pid}&qid={qid}"
                    )


            self.player_interrupts.pop(h_pid)

        self.update_now_playing_media(transport, h_pid)

    def get_player_components(self, device_uid, pid=None):
        from .controllers import HeosPlayer
        hplayers = HPlayer.objects.filter(device__uid=device_uid)
        if pid:
            hplayers = hplayers.filter(pid=pid)
        hplayer_ids = [hp.id for hp in hplayers]
        return Component.objects.filter(
            controller_uid=HeosPlayer.uid, config__hplayer__in=hplayer_ids
        )

    def read_transport_buffers(self):
        for uid, transport in self.transporters.items():
            transport.receive()
            while transport.buffer.qsize():
                data = transport.buffer.get()
                #print(f"DATA RECEIVED from {uid}: {data}")
                try:
                    self.receive_event(transport, data)
                except:
                    print(traceback.format_exc(), file=sys.stderr)
                    continue


    def update_now_playing_media(self, transport, player_pid):
        resp = transport.cmd(
            f"heos://player/get_play_state?pid={player_pid}"
        )
        if not resp or resp.status != 'success':
            return
        player_state = self.states_map.get(resp.values['state'])
        mode = transport.cmd(
            f'heos://player/get_play_mode?pid={player_pid}'
        )
        if not mode or mode.status != 'success':
            return

        volume = None
        denon_resp = transport.denon_cmd('MV?', True)
        if denon_resp:
            for r in denon_resp:
                if r.startswith('MV'):
                    try:
                        volume = int(r[2:])
                    except:
                        pass
                    break

        ZM = True
        denon_resp = transport.denon_cmd('ZM?', True)
        if denon_resp:
            for r in denon_resp:
                if r.startswith('ZM'):
                    if r == 'ZMON':
                        ZM = True
                    else:
                        ZM = False
                    break

        Z2 = False
        denon_resp = transport.denon_cmd('Z2?', True)
        if denon_resp:
            for r in denon_resp:
                if r.startswith('Z2'):
                    if r == 'Z2ON':
                        Z2 = True
                    else:
                        Z2 = False
                    break

        resp = transport.cmd(
            f'heos://player/get_now_playing_media?pid={player_pid}'
        )
        if not resp or resp.status != 'success':
            return
        for comp in self.get_player_components(transport.uid, player_pid):
            title = []

            if resp.payload.get('type') == 'station':
                if resp.payload.get('station'):
                    title.append(resp.payload.get('station'))

            ignore_vals = ['Url Stream']
            for attr in ['song', 'artist', 'album', 'album_id', 'mid']:
                v = resp.payload.get(attr)
                if not v:
                    continue
                if v in ignore_vals:
                    continue
                if v in title:
                    continue
                title.append(v)

            comp.meta['title'] = ' - '.join(title)
            comp.meta['image_url'] = resp.payload.get('image_url')

            comp.meta['shuffle'] = mode.values.get('shuffle') != 'off'
            comp.meta['loop'] = mode.values.get('repeat') != 'off'
            comp.meta['ZM'] = ZM
            comp.meta['Z2'] = Z2
            if volume:
                comp.meta['volume'] = volume

            comp.save()
            comp.set(player_state)


    def play_library_item(
        self, transport, pid, component, item, volume=None, fade_in=None
    ):
        if component.value == 'playing':
            transport.cmd(
                f"heos://player/set_play_state?pid={pid}&state=stopped"
            )
        denon_source = 'SITV'
        denon_resp = transport.denon_cmd('SI?', True)
        if denon_resp:
            for r in denon_resp:
                if r.startswith('SI'):
                    denon_source = r

        if denon_source != 'SINET':
            transport.denon_cmd(f"MUON")
            time.sleep(0.5)
            transport.denon_cmd(f"SINET")
            time.sleep(0.5)
            transport.denon_cmd(f"MUOFF")
            time.sleep(0.5)

        if not any([component.config.get('ZM'), component.config.get('Z2')]):
            transport.denon_cmd(f"ZMON")
            time.sleep(0.5)

        current_volume = volume
        if fade_in:
            current_volume = 0
        if volume:
            transport.denon_cmd(f"MV{current_volume:02}")

        if item['type'] == 'station':
            transport.cmd(
                f"heos://browse/play_stream?pid={pid}&sid=3"
                f"&cid=1&mid={item['mid']}&name={item['name']}"
            )
        if item['type'] == 'playlist':
            transport.cmd(f"heos://player/clear_queue?pid={pid}")
            transport.cmd(
                f"heos://browse/add_to_queue?pid={pid}&sid=1025"
                f"&cid={item['cid']}&aid=1"
            )

        if fade_in:
            fade_step = volume / (fade_in * 4)
            for i in range(fade_in * 4):
                current_volume = int((i + 1) * fade_step)
                transport.denon_cmd(f"MV{current_volume:02}")
                time.sleep(0.25)
        elif volume:
            for i in range(2):
                transport.denon_cmd(f"MV{current_volume:02}")
                time.sleep(0.5)


    def receive_event(self, transport, data):
        values = transport.parse_values(data)
        command = data['heos']['command']
        if command == 'system/sign_in':
            if data['heos']['result'] == 'fail':
                for comp in self.get_player_components(transport.uid):
                    comp.error_msg = f"Sign In error: {data['heos']['message']}"
                    comp.save()
            elif data['heos']['result'] == 'success':
                for comp in self.get_player_components(transport.uid):
                    comp.error_msg = None
                    comp.save()
        if command == 'event/player_now_playing_progress':
            for comp in self.get_player_components(transport.uid, values['pid']):
                comp.meta['position'] = values['cur_pos']
                comp.meta['duration'] = values['duration']
                comp.save()
        elif command == 'event/player_state_changed':
            for comp in self.get_player_components(transport.uid, values['pid']):
                comp.set(self.states_map.get(values['state']))
            if values['state'] == 'stop' \
            and f"{transport.uid}_{values['pid']}" in self.playing_alerts:
                self.finish_alert(transport, values['pid'])
        elif command == 'event/player_now_playing_changed':
            self.update_now_playing_media(transport, values['pid'])
            if f"{transport.uid}_{values['pid']}" in self.playing_alerts:
                self.finish_alert(transport, values['pid'])
        elif command == 'event/player_volume_changed':
            for comp in self.get_player_components(transport.uid, values['pid']):
                comp.meta['volume'] = values['level']
                comp.save()
