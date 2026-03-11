from django import forms
from .models import Room, Server


class ServerForm(forms.ModelForm):
    class Meta:
        model = Server
        fields = ('name', 'description', 'is_public')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


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
