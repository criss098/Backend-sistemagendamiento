from django.db import models

class Cita(models.Model):
    nombre = models.CharField(max_length=100)
    email = models.EmailField()
    motivo = models.TextField()
    telefono = models.CharField(max_length=15)
    fecha = models.DateField()
    hora = models.IntegerField()  # Hora solo como entero, ej: 9, 15, 17

    def __str__(self):
        return f'Cita con {self.nombre} el {self.fecha} a las {str(self.hora).zfill(2)}:00'
