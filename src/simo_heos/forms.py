from django import forms
from simo.core.forms import BaseComponentForm


class HEOSPlayerConfigForm(BaseComponentForm):
    username = forms.CharField(
        label="HEOS account username",
        blank=True, null=True,
        help_text="Porviding HEOS account credentials allows SIMO.io "
                  "to see and use your HEOS favorites, saved playlists, etc."
    )
    password = forms.CharField(
        label="HEOS account password",
        blank=True, null=True,
    )