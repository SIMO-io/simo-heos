from django.apps import AppConfig


class SIMOHEOSAppConfig(AppConfig):
    name = 'simo_heos'

    _setup_done = False

    def ready(self):
        if self._setup_done:
            return
        self._setup_done = True

        from simo.core.models import Gateway

        # database might be not intiated yet
        try:
            gw, new = Gateway.objects.get_or_create(
                type='simo_heos.gateways.HEOSGatewayHandler'
            )
        except:
            return
        if new:
            gw.start()