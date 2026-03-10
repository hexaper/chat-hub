from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Room, RoomParticipant
from .forms import RoomForm, RoomPasswordForm


@login_required
def room_list(request):
    rooms = Room.objects.filter(is_active=True)
    return render(request, 'rooms/room_list.html', {'rooms': rooms})


@login_required
def room_create(request):
    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.host = request.user
            room.save()
            RoomParticipant.objects.create(room=room, user=request.user)
            return redirect('room_detail', slug=room.slug)
    else:
        form = RoomForm()
    return render(request, 'rooms/room_create.html', {'form': form})


@login_required
def room_detail(request, slug):
    room = get_object_or_404(Room, slug=slug, is_active=True)

    # Password gate (host is always allowed in)
    if room.is_password_protected and room.host != request.user:
        session_key = f'room_auth_{slug}'
        if not request.session.get(session_key):
            if request.method == 'POST':
                form = RoomPasswordForm(request.POST)
                if form.is_valid():
                    if form.cleaned_data['password'] == room.password:
                        request.session[session_key] = True
                    else:
                        form.add_error('password', 'Incorrect password.')
                        return render(request, 'rooms/room_password.html', {'room': room, 'form': form})
            else:
                return render(request, 'rooms/room_password.html', {'room': room, 'form': RoomPasswordForm()})

    participant, _ = RoomParticipant.objects.get_or_create(room=room, user=request.user)
    participants = RoomParticipant.objects.filter(room=room).select_related('user')
    return render(request, 'rooms/room_detail.html', {
        'room': room,
        'participant': participant,
        'participants': participants,
        'is_host': room.host == request.user,
    })


@login_required
def room_leave(request, slug):
    room = get_object_or_404(Room, slug=slug)
    RoomParticipant.objects.filter(room=room, user=request.user).delete()
    messages.info(request, f'You left {room.name}.')
    return redirect('room_list')


@login_required
def room_delete(request, slug):
    room = get_object_or_404(Room, slug=slug, host=request.user, is_active=True)
    if request.method == 'POST':
        room.is_active = False
        room.save()
        # Notify all connected WebSocket clients
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'room_{slug}',
            {'type': 'room_closed'},
        )
        messages.success(request, f'Room "{room.name}" has been closed.')
        return redirect('room_list')
    return redirect('room_detail', slug=slug)
