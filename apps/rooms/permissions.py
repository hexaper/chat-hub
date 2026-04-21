from .models import ServerMember


def get_membership(server, user):
    if not user.is_authenticated:
        return None
    return ServerMember.objects.filter(server=server, user=user).first()


def is_server_owner(server, user):
    return user.is_authenticated and server.owner_id == user.id


def is_server_admin(server, user):
    membership = get_membership(server, user)
    return bool(membership and membership.role == ServerMember.ROLE_ADMIN)


def can_moderate_server(server, user):
    return is_server_owner(server, user) or is_server_admin(server, user) or user.is_staff


def can_manage_server_settings(server, user):
    return is_server_owner(server, user) or user.is_staff
