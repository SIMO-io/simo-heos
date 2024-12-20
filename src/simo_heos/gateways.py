import sys, traceback
from simo.core.gateways import BaseObjectCommandsGatewayHandler
from simo.core.forms import BaseGatewayForm
from simo.core.middleware import drop_current_instance
from simo.core.models import Component
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transporters = {}
        self.player_transporters = {}
        self.player_interrupts = {}

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
            authorize_transports[hplayer.device] = {
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
                self.update_library(device)
                continue
            transport.authorize(credentials['un'], credentials['pw'])


    def update_library(self, device):
        print("Update library!")
        pass


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
            resp = transport.cmd(
                f"heos://player/set_volume?pid={hplayer.pid}"
                f"&level={value['set_volume']}"
            )
            if resp and resp.status == 'success':
                component.meta['volume'] = value['set_volume']
                component.save()

        if 'loop' in value:
            resp = transport.cmd(
                'heos://player/get_play_mode?pid={hplayer.pid}'
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
                'heos://player/get_play_mode?pid={hplayer.pid}'
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

        if 'play_alert' in value:

            resp = transport.cmd(
                f"heos://player/set_play_state?pid={hplayer.pid}&state=stop"
            )
            if not resp or resp.status != 'success':
                return

            # save current state if nothing is saved
            if hplayer.pid not in self.player_interrupts:
                resp = transport.cmd(
                    f'heos://player/get_now_playing_media?pid={hplayer.pid}'
                )
                if resp and resp.status == 'success':
                    resp.payload.update({
                        'volume': component.meta['volume'],
                        'shuffle': component.meta['shuffle'],
                        'loop': component.meta['loop']
                    })
                    self.player_interrupts[hplayer.pid] = resp.payload


            if value.get('volume'):
                component.meta['volume'] = value['set_volume']
                resp = transport.cmd(
                    f"heos://player/set_volume?pid={hplayer.pid}"
                    f"&level={value['volume']}"
                )
                if resp and resp.status == 'success':
                    pass


            component.meta['loop'] = value.get('loop', False)
            resp = transport.cmd(
                f"heos://player/set_play_mode?pid={hplayer.pid}"
                f"&repeat={'on_all' if component.meta['loop'] else 'off'}"
                f"&shuffle={'on' if component.meta['shuffle'] else 'off'}"
            )
            if resp and resp.status == 'success':
                component.meta['loop'] = value['loop']

            component.save()


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
                print(f"DATA RECEIVED from {uid}: {data}")
                try:
                    self.receive_event(transport, data)
                except:
                    print(traceback.format_exc(), file=sys.stderr)
                    continue


    def update_now_playing_media(self, transport, player_pid):
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
            if resp.payload.get('song'):
                title.append(resp.payload.get('song'))
            if resp.payload.get('artist'):
                title.append(resp.payload.get('artist'))

            if not title:
                if resp.payload.get('album'):
                    title.append(resp.payload.get('album'))

            if not title:
                if resp.payload.get('album_id'):
                    title.append(resp.payload.get('album_id'))

            if not title:
                if resp.payload.get('mid'):
                    title.append(resp.payload.get('mid'))

            comp.meta['title'] = ' - '.join(title)

            comp.meta['image_url'] = resp.payload.get('image_url')
            comp.save()


    def receive_event(self, transport, data):
        values = transport.parse_values(data)
        command = data['heos']['command']
        if command == 'system/sign_in':
            if data['heos']['result'] == 'fail':
                for comp in self.get_player_components(transport.uid):
                    comp.error_msg = f"Sign In error: Cannot connect to Web Services"
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
            states_map = {
                'stop': 'stopped', 'play': 'playing', 'pause': 'paused'
            }
            for comp in self.get_player_components(transport.uid, values['pid']):
                comp.set(states_map.get(values['state']))
        elif command == 'event/player_now_playing_changed':
            self.update_now_playing_media(transport, values['pid'])



