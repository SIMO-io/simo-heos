import sys, traceback
from simo.core.gateways import BaseObjectCommandsGatewayHandler
from simo.core.forms import BaseGatewayForm
from simo.core.middleware import drop_current_instance
from simo.core.models import Component
from .utils import discover_heos_devices
from .transport import HEOSDeviceTransporter
from .models import HeosDevice, HeosPlayer


class HEOSGatewayHandler(BaseObjectCommandsGatewayHandler):
    name = "DENON HEOS"
    config_form = BaseGatewayForm

    periodic_tasks = (
        ('discover_devices', 60),
        ('watch_players', 1)
    )

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.transporters = {}
        self.player_transporters = {}

    def discover_devices(self):
        from .controllers import HeosPlayer
        active_players = []
        for d_info in discover_heos_devices():
            if d_info['uid'] not in self.transporters \
            or self.transporters[d_info['uid']].ip != d_info['ip']:
                try:
                    self.transporters[d_info['uid']] = HEOSDeviceTransporter(
                        d_info['ip'], d_info['uid']
                    )
                except:
                    print(traceback.format_exc(), file=sys.stderr)
                    continue
            transporter = self.heos_devices[d_info['uid']]
            try:
                resp = transporter.cmd('heos://player/get_players')
            except:
                print(traceback.format_exc(), file=sys.stderr)
                self.transporters.pop(d_info['uid'])
                continue
            if not resp or resp['status'] != ['success']:
                continue

            heos_device, new = HeosDevice.objects.update_or_create(
                uid=d_info['uid'], defaults={
                    'ip': d_info['ip'], 'name': d_info['name'],
                    'connected': True
                }
            )

            for player_info in resp['payload']:
                player, new = HeosPlayer.objects.update_or_create(
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
