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
        #('watch_players', 1)
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transporters = {}
        self.player_transporters = {}

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
            if not resp or resp['status'] != 'success':
                print(f"Bad respponse: {resp}")
                continue

            heos_device, new = HeosDevice.objects.update_or_create(
                uid=d_info['uid'], defaults={
                    'ip': d_info['ip'], 'name': d_info['name'],
                    'connected': True
                }
            )
            active_devices.append(heos_device.id)

            for player_info in resp['payload']:
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
            hplayer = HPlayer.objects.get(
                id=component.config['hplayer']
            ).select_related('device')
            authorize_transports[hplayer.device] = {
                'un': component.config.get('username'),
                'pw': component.config.get('password')
            }

        for device, credentials in authorize_transports.items():
            transport = self.transporters[device.uid]
            resp = transport.cmd('heos://system/check_account')
            if not resp or resp['status'] != 'success':
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

        hplayer = HPlayer.objects.get(
            id=component.config['hplayer']
        ).select_related('device')
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
            if resp and resp['status'] == 'success':
                component.meta['volume'] = value['set_volume']
                component.save()

        if 'loop' in value:
            resp = transport.cmd(
                'heos://player/get_play_mode?pid={hplayer.pid}'
            )
            if not resp or resp['status'] != 'success':
                return
            component.meta['shuffle'] = resp.values.get('shuffle') != 'off'
            component.meta['loop'] = resp.values.get('repeat') != 'off'
            resp = transport.cmd(
                f"heos://player/set_play_mode?pid={hplayer.pid}"
                f"&repeat={'on_all' if component.meta['loop'] else 'off'}"
                f"&shuffle={'on' if component.meta['shuffle'] else 'off'}"
            )
            if resp and resp['status'] == 'success':
                component.meta['loop'] = value['loop']
            component.save()

        if 'shuffle' in value:
            resp = transport.cmd(
                'heos://player/get_play_mode?pid={hplayer.pid}'
            )
            if not resp or resp['status'] != 'success':
                return
            component.meta['shuffle'] = resp.values.get('shuffle') != 'off'
            component.meta['loop'] = resp.values.get('repeat') != 'off'
            resp = transport.cmd(
                f"heos://player/set_play_mode?pid={hplayer.pid}"
                f"&repeat={'on_all' if component.meta['loop'] else 'off'}"
                f"&shuffle={'on' if component.meta['shuffle'] else 'off'}"
            )
            if resp and resp['status'] == 'success':
                component.meta['shuffle'] = value['shuffle']
            component.save()



