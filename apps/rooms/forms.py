from django import forms
from .models import Room


class RoomForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text='Leave blank for no password.',
    )

    class Meta:
        model = Room
        fields = ('name', 'password')


class RoomPasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label='Room Password')
