from django.db import models


class HeosDevice(models.Model):
    uid = models.CharField()
    name = models.CharField()
    ip = models.GenericIPAddressField()
    connected = models.BooleanField(default=False, editable=False)
    username = models.CharField(
        "HEOS account username", blank=True, null=True,
        help_text="Porviding HEOS account credentials allows SIMO.io "
                  "to see and use your HEOS favorites, saved playlists, etc."
    )
    password = models.CharField("HEOS account password", blank=True, null=True)


class HeosPlayer(models.Model):
    device = models.ForeignKey(HeosDevice, on_delete=models.CASCADE)
    name = models.CharField()
    pid = models.IntegerField()