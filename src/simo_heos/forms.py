from django import forms
from simo.core.forms import BaseComponentForm
from simo.core.form_fields import PasswordField
from .models import HPlayer


class HEOSPlayerConfigForm(BaseComponentForm):
    username = forms.CharField(
        label="HEOS account username",
        required=False,
        help_text="Porviding HEOS account credentials allows SIMO.io "
                  "to see and use your HEOS favorites, saved playlists, etc."
    )
    password = PasswordField(
        label="HEOS account password", required=False
    )
    hplayer = forms.ModelChoiceField(
        label='HEOS Player',
        queryset=HPlayer.objects.filter(device__connected=True)
    )