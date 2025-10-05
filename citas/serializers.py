from rest_framework import serializers
from .models import Cita


class CitaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cita
        fields = '__all__'
        

# class Formulario1Serializer(serializers.ModelSerializer):
#     class Meta:
#         model = Formulario1
#         fields = '__all__'
