from django.urls import path
from . import views

urlpatterns = [
    path('', views.room_list, name='room_list'),
    path('create/', views.room_create, name='room_create'),
    path('<uuid:slug>/', views.room_detail, name='room_detail'),
    path('<uuid:slug>/leave/', views.room_leave, name='room_leave'),
    path('<uuid:slug>/delete/', views.room_delete, name='room_delete'),
]
