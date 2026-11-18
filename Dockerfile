# Imagen base con Python
FROM python:3.12-slim

# Muestra los mensajes de Python al instante en "docker logs"
ENV PYTHONUNBUFFERED=1

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

# Primero las dependencias (aprovecha la caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Luego el código de la aplicación y la carpeta static (logo)
COPY app.py .
COPY static/ static/

# Puerto en el que escucha la app
EXPOSE 5000

# Comando de inicio
CMD ["python", "app.py"]
