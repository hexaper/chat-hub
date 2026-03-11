from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST as require_post_method

from .models import Server, ServerMember, Room, RoomParticipant
from .forms import ServerForm, RoomForm, RoomPasswordForm


# ── Server views ──────────────────────────────────────────────────────────────

@login_required
def server_list(request):
    my_servers = Server.objects.filter(members=request.user).distinct()
    public_servers = Server.objects.filter(is_public=True).exclude(members=request.user)
    return render(request, 'rooms/server_list.html', {
        'my_servers': my_servers,
        'public_servers': public_servers,
    })


@login_required
def server_create(request):
    if request.method == 'POST':
        form = ServerForm(request.POST)
        if form.is_valid():
            server = form.save(commit=False)
            server.owner = request.user
            server.save()
            ServerMember.objects.create(server=server, user=request.user)
            return redirect('server_detail', server_slug=server.slug)
    else:
        form = ServerForm()
    return render(request, 'rooms/server_create.html', {'form': form})


@login_required
def server_detail(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    is_member = ServerMember.objects.filter(server=server, user=request.user).exists()

    if not is_member:
        if server.is_public:
            ServerMember.objects.create(server=server, user=request.user)
            is_member = True
        else:
            messages.error(request, 'You need an invite to join this server.')
            return redirect('server_list')

    # Clean up rooms empty for 15+ minutes
    threshold = timezone.now() - timedelta(minutes=15)
    Room.objects.filter(
        server=server, is_active=True,
        last_empty_at__isnull=False, last_empty_at__lte=threshold,
    ).update(is_active=False)

    rooms = Room.objects.filter(server=server, is_active=True)
    is_owner = server.owner == request.user
    member_count = ServerMember.objects.filter(server=server).count()

    return render(request, 'rooms/server_detail.html', {
        'server': server,
        'rooms': rooms,
        'is_owner': is_owner,
        'member_count': member_count,
    })


@login_required
def server_join(request):
    code = request.GET.get('code') or request.POST.get('invite_code')
    if code:
        try:
            server = Server.objects.get(invite_code=code)
        except Server.DoesNotExist:
            messages.error(request, 'Invalid invite code.')
            return redirect('server_list')
        ServerMember.objects.get_or_create(server=server, user=request.user)
        messages.success(request, f'You joined {server.name}!')
        return redirect('server_detail', server_slug=server.slug)
    return redirect('server_list')


# ── Room views ────────────────────────────────────────────────────────────────

@login_required
def room_create(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if not ServerMember.objects.filter(server=server, user=request.user).exists():
        messages.error(request, 'You must be a server member to create rooms.')
        return redirect('server_list')

    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.host = request.user
            room.server = server
            room.set_password(form.cleaned_data.get('password', ''))
            room.save()
            RoomParticipant.objects.create(room=room, user=request.user)
            return redirect('room_detail', server_slug=server.slug, slug=room.slug)
    else:
        form = RoomForm()
    return render(request, 'rooms/room_create.html', {'form': form, 'server': server})


@login_required
def room_detail(request, server_slug, slug):
    server = get_object_or_404(Server, slug=server_slug)
    room = get_object_or_404(Room, slug=slug, server=server, is_active=True)

    if not ServerMember.objects.filter(server=server, user=request.user).exists():
        messages.error(request, 'You must be a server member.')
        return redirect('server_list')

    # Password gate (host is always allowed in)
    if room.is_password_protected and room.host != request.user:
        session_key = f'room_auth_{slug}'
        if not request.session.get(session_key):
            if request.method == 'POST':
                form = RoomPasswordForm(request.POST)
                if form.is_valid():
                    if room.check_room_password(form.cleaned_data['password']):
                        request.session[session_key] = True
                    else:
                        form.add_error('password', 'Incorrect password.')
                        return render(request, 'rooms/room_password.html', {
                            'room': room, 'form': form, 'server': server,
                        })
            else:
                return render(request, 'rooms/room_password.html', {
                    'room': room, 'form': RoomPasswordForm(), 'server': server,
                })

    participant, _ = RoomParticipant.objects.get_or_create(room=room, user=request.user)
    participants = RoomParticipant.objects.filter(room=room).select_related('user')
    return render(request, 'rooms/room_detail.html', {
        'room': room,
        'server': server,
        'participant': participant,
        'participants': participants,
        'is_host': room.host == request.user,
    })


@login_required
@require_post_method
def room_leave(request, server_slug, slug):
    server = get_object_or_404(Server, slug=server_slug)
    room = get_object_or_404(Room, slug=slug, server=server)
    RoomParticipant.objects.filter(room=room, user=request.user).delete()
    messages.info(request, f'You left {room.name}.')
    return redirect('server_detail', server_slug=server.slug)


@login_required
def room_delete(request, server_slug, slug):
    server = get_object_or_404(Server, slug=server_slug)
    room = get_object_or_404(Room, slug=slug, server=server, host=request.user, is_active=True)
    if request.method == 'POST':
        room.is_active = False
        room.save()
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'room_{slug}',
            {'type': 'room_closed'},
        )
        messages.success(request, f'Room "{room.name}" has been closed.')
        return redirect('server_detail', server_slug=server.slug)
    return redirect('room_detail', server_slug=server.slug, slug=slug)
