from simo.multimedia.controllers import BaseAudioPlayer
from .forms import HEOSPlayerConfigForm
from .gateways import HEOSGatewayHandler


class HeosPlayer(BaseAudioPlayer):
    gateway_class = HEOSGatewayHandler
    name = "HEOS Player"
    config_form = HEOSPlayerConfigForm
    manual_add = True


