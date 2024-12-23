from simo.multimedia.controllers import BaseAudioPlayer
from .forms import HEOSPlayerConfigForm
from .gateways import HEOSGatewayHandler


class HeosPlayer(BaseAudioPlayer):
    gateway_class = HEOSGatewayHandler
    name = "HEOS Player"
    config_form = HEOSPlayerConfigForm
    manual_add = True

    def zm(self, on):
        self.send({"ZM": on})

    def z2(self, on):
        self.send({"Z2": on})
