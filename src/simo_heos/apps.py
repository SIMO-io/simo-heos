from django.apps import AppConfig


class SIMOHEOSAppConfig(AppConfig):
    name = 'simo_heos'

    _setup_done = False

    def ready(self):
        if self._setup_done:
            return
        self._setup_done = True

        from simo.core.models import Gateway

        gw, new = Gateway.objects.get_or_create(
            type='simo_heos.gateways.HEOSGatewayHandler'
        )
        if new:
            gw.start()