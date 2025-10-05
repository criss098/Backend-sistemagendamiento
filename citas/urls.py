from django.urls import path
from . import views

urlpatterns = [ 
    path('google/login/', views.google_login, name='google_login'),
    path('auth/callback/', views.auth_callback, name='auth_callback'),
    path('crear-evento/', views.crear_evento, name='crear_evento'),
    path('obtener-horas-ocupadas/', views.obtener_horas_ocupadas, name='obtener_horas_ocupadas'),
    path('obtener-horas-disponibles/', views.obtener_horas_disponibles, name='obtener_horas_disponibles'),
    
]
