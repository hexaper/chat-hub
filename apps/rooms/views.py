from datetime import timedelta
from functools import wraps
from io import BytesIO

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Prefetch
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST as require_post_method
from PIL import Image

from .models import Server, ServerMember, Room, RoomParticipant, ChatMessage
from .forms import ServerForm, ServerSettingsForm, RoomForm, RoomPasswordForm

User = get_user_model()


def _is_admin(user):
    return user.is_authenticated and user.is_staff


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _is_admin(request.user):
            messages.error(request, 'Admin access required.')
            return redirect('server_list')
        return view_func(request, *args, **kwargs)
    return wrapper


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
        form = ServerForm(request.POST, request.FILES)
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

    rooms = Room.objects.filter(server=server, is_active=True).annotate(
        participant_count=Count('roomparticipant')
    )
    is_owner = server.owner == request.user
    member_count = ServerMember.objects.filter(server=server).count()

    return render(request, 'rooms/server_detail.html', {
        'server': server,
        'rooms': rooms,
        'is_owner': is_owner,
        'member_count': member_count,
    })


@login_required
@require_post_method
def server_join(request):
    code = request.POST.get('invite_code')
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


@login_required
def server_settings(request, server_slug):
    if _is_admin(request.user):
        server = get_object_or_404(Server, slug=server_slug)
    else:
        server = get_object_or_404(Server, slug=server_slug, owner=request.user)
    members = ServerMember.objects.filter(server=server).select_related('user').order_by('joined_at')

    if request.method == 'POST':
        form = ServerSettingsForm(request.POST, request.FILES, instance=server)
        if form.is_valid():
            form.save()
            messages.success(request, 'Server settings updated.')
            return redirect('server_settings', server_slug=server.slug)
    else:
        form = ServerSettingsForm(instance=server)

    return render(request, 'rooms/server_settings.html', {
        'server': server,
        'form': form,
        'members': members,
    })


@login_required
@require_post_method
def server_kick_member(request, server_slug):
    if _is_admin(request.user):
        server = get_object_or_404(Server, slug=server_slug)
    else:
        server = get_object_or_404(Server, slug=server_slug, owner=request.user)
    user_id = request.POST.get('user_id')
    if str(user_id) == str(server.owner_id):
        messages.error(request, "You can't remove yourself as owner.")
    else:
        removed = ServerMember.objects.filter(server=server, user_id=user_id).delete()[0]
        if removed:
            messages.success(request, 'Member removed.')
        else:
            messages.error(request, 'Member not found.')
    return redirect('server_settings', server_slug=server.slug)


@login_required
@require_post_method
def server_regenerate_invite(request, server_slug):
    if _is_admin(request.user):
        server = get_object_or_404(Server, slug=server_slug)
    else:
        server = get_object_or_404(Server, slug=server_slug, owner=request.user)
    server.regenerate_invite_code()
    messages.success(request, 'Invite code regenerated.')
    return redirect('server_settings', server_slug=server.slug)


@login_required
@require_post_method
def server_leave(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if server.owner == request.user:
        messages.error(request, "You can't leave your own server. Delete it instead.")
        return redirect('server_settings', server_slug=server.slug)
    ServerMember.objects.filter(server=server, user=request.user).delete()
    messages.info(request, f'You left {server.name}.')
    return redirect('server_list')


@login_required
@require_post_method
def server_delete(request, server_slug):
    if _is_admin(request.user):
        server = get_object_or_404(Server, slug=server_slug)
    else:
        server = get_object_or_404(Server, slug=server_slug, owner=request.user)
    name = server.name
    server.delete()
    messages.success(request, f'Server "{name}" deleted.')
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
    if _is_admin(request.user):
        room = get_object_or_404(Room, slug=slug, server=server, is_active=True)
    else:
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
        if _is_admin(request.user):
            return redirect('admin_panel')
        return redirect('server_detail', server_slug=server.slug)
    return redirect('room_detail', server_slug=server.slug, slug=slug)


# ── Chat image upload ────────────────────────────────────────────────────────

@login_required
@require_post_method
def chat_image_upload(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    if not ServerMember.objects.filter(server=server, user=request.user).exists():
        return JsonResponse({'error': 'Not a member'}, status=403)

    image = request.FILES.get('image')
    if not image:
        return JsonResponse({'error': 'No image provided'}, status=400)

    if image.size > 5 * 1024 * 1024:
        return JsonResponse({'error': 'Image too large (max 5MB)'}, status=400)

    # Validate actual image content (not just Content-Type header)
    try:
        img = Image.open(image)
        img.verify()
        image.seek(0)
    except Exception:
        return JsonResponse({'error': 'Invalid image file'}, status=400)

    if img.format not in ('JPEG', 'PNG', 'GIF', 'WEBP'):
        return JsonResponse({'error': 'Invalid image type'}, status=400)

    msg = ChatMessage.objects.create(
        server=server,
        user=request.user,
        image=image,
    )
    return JsonResponse({
        'image_url': msg.image.url,
        'message_id': msg.id,
    })


# ── Admin panel views ────────────────────────────────────────────────────────

@admin_required
def admin_panel(request):
    servers = Server.objects.prefetch_related(
        'servermember_set__user',
        Prefetch('rooms', queryset=Room.objects.filter(is_active=True), to_attr='active_rooms'),
    ).all().order_by('-created_at')

    # All users with their server names
    all_users = User.objects.prefetch_related('joined_servers').order_by('-date_joined')
    for u in all_users:
        server_names = [s.name for s in u.joined_servers.all()]
        u.server_list = ', '.join(server_names) if server_names else ''

    # Users not in any server
    users_without_server = User.objects.exclude(
        id__in=ServerMember.objects.values_list('user_id', flat=True)
    )

    total_users = User.objects.count()
    total_servers = servers.count()
    total_rooms = Room.objects.filter(is_active=True).count()

    return render(request, 'rooms/admin_panel.html', {
        'servers': servers,
        'all_users': all_users,
        'users_without_server': users_without_server,
        'total_users': total_users,
        'total_servers': total_servers,
        'total_rooms': total_rooms,
    })


@admin_required
@require_post_method
def admin_delete_server(request, server_slug):
    server = get_object_or_404(Server, slug=server_slug)
    name = server.name
    server.delete()
    messages.success(request, f'Server "{name}" deleted.')
    return redirect('admin_panel')


@admin_required
@require_post_method
def admin_delete_room(request, server_slug, slug):
    server = get_object_or_404(Server, slug=server_slug)
    room = get_object_or_404(Room, slug=slug, server=server, is_active=True)
    room.is_active = False
    room.save()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'room_{slug}',
        {'type': 'room_closed'},
    )
    messages.success(request, f'Room "{room.name}" closed.')
    return redirect('admin_panel')


@admin_required
@require_post_method
def admin_delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user.is_staff:
        messages.error(request, "Cannot delete an admin account.")
    else:
        username = user.username
        user.delete()
        messages.success(request, f'User "{username}" deleted.')
    return redirect('admin_panel')
