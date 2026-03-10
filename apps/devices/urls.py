from django.urls import path
from . import views

urlpatterns = [
    path('', views.device_list, name='device_list'),
    path('register/', views.register_device, name='register_device'),
    path('<int:pk>/set-default/', views.set_default_device, name='set_default_device'),
]
