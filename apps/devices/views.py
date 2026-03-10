from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
from .models import Device


@login_required
def device_list(request):
    devices = Device.objects.filter(user=request.user)
    return render(request, 'devices/device_list.html', {'devices': devices})


@login_required
@require_POST
def register_device(request):
    data = json.loads(request.body)
    device, created = Device.objects.update_or_create(
        user=request.user,
        device_id=data['deviceId'],
        defaults={
            'label': data.get('label', ''),
            'device_type': data['deviceType'],
        }
    )
    return JsonResponse({'id': device.id, 'created': created})


@login_required
@require_POST
def set_default_device(request, pk):
    device = get_object_or_404(Device, pk=pk, user=request.user)
    Device.objects.filter(user=request.user, device_type=device.device_type).update(is_default=False)
    device.is_default = True
    device.save()
    return JsonResponse({'status': 'ok'})
