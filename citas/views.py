from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from datetime import datetime, timedelta
import json
import pytz
import os
import pathlib
from django.shortcuts import redirect
from django.conf import settings
import urllib.parse
import requests
import logging

logger = logging.getLogger(__name__)

# === Configuración ===
CALENDAR_ID = "contacto@fortalezalegal.cl"  # tu correo/correo del calendario
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
TOKEN_FILE = os.path.join(BASE_DIR, 'admin_token.json')

def google_login(request):
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile https://www.googleapis.com/auth/calendar.events",
        "access_type": "offline",
        "prompt": "consent"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    return redirect(url)

def auth_callback(request):
    code = request.GET.get('code')

    if not code:
        return JsonResponse({'error': 'No se recibió el código de autorización'}, status=400)

    token_url = 'https://oauth2.googleapis.com/token'
    data = {
        'code': code,
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code'
    }

    response = requests.post(token_url, data=data)
    token_data = response.json()

    if response.status_code == 200:
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')

        # Redirige al frontend con tokens en la URL
        frontend_url = f"http://localhost:3000/?token={access_token}&refresh_token={refresh_token}"
        return redirect(frontend_url)
    else:
        return JsonResponse({
            'error': 'Fallo al obtener el token',
            'status_code': response.status_code,
            'details': token_data
        }, status=400)



def get_token_admin():
    with open(TOKEN_FILE, 'r') as f:
        data = json.load(f)

    creds = Credentials(
        token=data['token'],
        refresh_token=data.get('refresh_token'),
        token_uri=data['token_uri'],
        client_id=data['client_id'],
        client_secret=data['client_secret'],
        scopes=data['scopes'],
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w') as f:
            json.dump({
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes,
            }, f)

    return creds

@csrf_exempt
def crear_evento(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        body = json.loads(request.body)

        usar_token_admin = body.get('usar_token_admin', False)
        if usar_token_admin:
            creds = get_token_admin()
        else:
            access_token = body.get('access_token')
            if not access_token:
                return JsonResponse({'error': 'Token no proporcionado'}, status=400)
            creds = Credentials(token=access_token)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())

        service = build('calendar', 'v3', credentials=creds)

        nombres = body.get('nombres')
        apellidos = body.get('apellidos')
        correo = body.get('correo')
        motivo = body.get('motivo')
        fecha = body.get('fecha')  # YYYY-MM-DD
        hora = body.get('hora')    # HH:MM

        if not all([nombres, apellidos, correo, motivo, fecha, hora]):
            return JsonResponse({'error': 'Faltan datos del evento'}, status=400)

        zona = pytz.timezone("America/Santiago")
        dt_inicio = zona.localize(datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M"))
        dt_fin = dt_inicio + timedelta(hours=1)

        evento = {
            'summary': f'Cita: {nombres} {apellidos}',
            'description': motivo,
            'start': {
                'dateTime': dt_inicio.isoformat(),
                'timeZone': 'America/Santiago',
            },
            'end': {
                'dateTime': dt_fin.isoformat(),
                'timeZone': 'America/Santiago',
            },
            'attendees': [{'email': correo}],
        }

        creado = service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        return JsonResponse({'mensaje': 'Evento creado correctamente', 'id': creado.get('id')})

    except Exception as e:
        logger.error(f"Error en crear_evento: {e}")
        return JsonResponse({'error': 'Error inesperado', 'detalle': str(e)}, status=500)

@csrf_exempt
def obtener_horas_ocupadas(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        fecha_str = data.get("fecha")
        access_token = data.get("access_token")

        if not fecha_str or not access_token:
            return JsonResponse({'error': 'Faltan parámetros requeridos'}, status=400)

        zona_horaria = pytz.timezone('America/Santiago')
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        inicio = zona_horaria.localize(datetime.combine(fecha, datetime.min.time())).isoformat()
        fin = zona_horaria.localize(datetime.combine(fecha, datetime.max.time())).isoformat()

        url = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"

        print("Fecha solicitada (del frontend):", fecha_str)
        print("Datetime inicio:", inicio)
        print("Datetime fin:", fin)

        params = {
            "timeMin": inicio,
            "timeMax": fin,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            logger.error(f"Error al obtener eventos: {response.text}")
            return JsonResponse({'error': 'Error al obtener eventos de Google Calendar'}, status=response.status_code)

        eventos = response.json().get("items", [])
        horas_ocupadas = []

        for evento in eventos:
            inicio_evento = evento["start"].get("dateTime")
            if inicio_evento:
                hora = inicio_evento.split("T")[1][:5]  # HH:MM
                horas_ocupadas.append(hora)

        return JsonResponse({"horas_ocupadas": horas_ocupadas})

    except Exception as e:
        logger.exception("Excepción al obtener horas ocupadas")
        return JsonResponse({'error': 'Error interno en el servidor'}, status=500)





@csrf_exempt
def obtener_horas_disponibles(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        access_token = data.get("access_token")

        if not access_token:
            return JsonResponse({'error': 'Token de acceso no proporcionado'}, status=400)

        zona_horaria = pytz.timezone('America/Santiago')
        hoy = datetime.now(zona_horaria).date()
        dias_disponibles = {}

        # Define el rango de horas disponibles por día (ej. de 9:00 a 18:00 cada hora)
        horas_posibles = [f"{h:02d}:00" for h in range(9, 18)]  # ["09:00", ..., "17:00"]

        for i in range(7):
            fecha = hoy + timedelta(days=i)

            # 🚫 Saltar sábados (5) y domingos (6)
            if fecha.weekday() in [5, 6]:
                continue

            inicio = zona_horaria.localize(datetime.combine(fecha, datetime.min.time())).isoformat()
            fin = zona_horaria.localize(datetime.combine(fecha, datetime.max.time())).isoformat()

            url = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
            params = {
                "timeMin": inicio,
                "timeMax": fin,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            headers = {
                "Authorization": f"Bearer {access_token}"
            }

            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.error(f"Error al obtener eventos: {response.text}")
                return JsonResponse({'error': 'Error al obtener eventos de Google Calendar'}, status=response.status_code)

            eventos = response.json().get("items", [])
            horas_ocupadas = []

            for evento in eventos:
                inicio_evento = evento["start"].get("dateTime")
                if inicio_evento:
                    hora = inicio_evento.split("T")[1][:5]  # HH:MM
                    horas_ocupadas.append(hora)

            # Calcula horas disponibles
            horas_disponibles = [hora for hora in horas_posibles if hora not in horas_ocupadas]
            dias_disponibles[str(fecha)] = horas_disponibles

        return JsonResponse({"horas_disponibles": dias_disponibles})

    except Exception as e:
        logger.exception("Excepción al obtener horas disponibles")
        return JsonResponse({'error': 'Error interno en el servidor'}, status=500)





# views.py
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import Cita
from django.conf import settings

@csrf_exempt
def crear_cita(request):
    if request.method == "POST":
        data = json.loads(request.body)

        cita = Cita.objects.create(
            nombre=data["nombre"],
            correo=data["correo"],
            telefono=data.get("telefono", ""),
            fecha=data["fecha"],
            hora=data["hora"],
            motivo=data.get("motivo", "")
        )

        # ✉️ Correo de confirmación al cliente
        asunto_cliente = "Confirmación de tu cita"
        mensaje_cliente = f"""
        Hola {cita.nombre},

        Tu cita ha sido agendada con éxito.
        📅 Fecha: {cita.fecha}
        ⏰ Hora: {cita.hora}
        📝 Motivo: {cita.motivo if cita.motivo else 'No especificado'}

        Te contactaremos si hay algún cambio.
        """

        send_mail(
            asunto_cliente,
            mensaje_cliente,
            settings.DEFAULT_FROM_EMAIL,
            [cita.correo],
            fail_silently=False,
        )

        # ✉️ Notificación al administrador
        asunto_admin = "Nueva cita registrada"
        mensaje_admin = f"""
        Se ha registrado una nueva cita:

        Cliente: {cita.nombre}
        Correo: {cita.correo}
        Teléfono: {cita.telefono}
        Fecha: {cita.fecha}
        Hora: {cita.hora}
        Motivo: {cita.motivo}
        """

        send_mail(
            asunto_admin,
            mensaje_admin,
            settings.DEFAULT_FROM_EMAIL,
            ["contacto@fortalezalegal.cl"],  # correo admin
            fail_silently=False,
        )

        return JsonResponse({"message": "Cita creada y correos enviados"})
