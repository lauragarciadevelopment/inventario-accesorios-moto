# Inventario de accesorios para moto

Aplicación web para controlar el inventario de una tienda de accesorios para motociclistas:
**guantes, chaquetas, reflectivos, candados con alarma y guayas**.
Construida con Python (Flask) y PostgreSQL, ejecutada con Docker.

## Funcionalidades
- Agregar productos (nombre, categoría, talla, precio, stock).
- Listar el inventario y filtrar por categoría.
- Eliminar productos.
- Resaltar los productos con stock bajo (3 unidades o menos).

## Requisitos
- Docker y Docker Compose instalados.

## Ejecutar desde cero
1. Clonar el repositorio y entrar a la carpeta.
2. Crear el archivo de variables de entorno:
   ```
   cp .env.example .env
   ```
   (en Windows: `copy .env.example .env`) y cambiar la contraseña.
3. Levantar los servicios:
   ```
   docker compose up -d --build
   ```
4. Abrir http://localhost:5000

## Entrega 1: solo el contenedor de la app
```
docker build -t inventario-accesorios .
docker run -d -p 5000:5000 --name app-accesorios inventario-accesorios
```
(Para la entrega 1 se puede usar una versión sin PostgreSQL, guardando los datos en memoria.)

## Comandos útiles (estado, logs, detención y reinicio)
Ejecutar dentro de la carpeta del proyecto:

| Acción | Comando | Qué se debe ver |
|---|---|---|
| Ver estado | `docker compose ps` | `app` y `db` en `Up ... (healthy)` |
| Ver logs de todo | `docker compose logs` | Mensajes de PostgreSQL y de la app |
| Ver logs de la app | `docker compose logs app` | `Conectando a la base de datos en el host 'db'...` y `Conexion OK` |
| Seguir logs en vivo | `docker compose logs -f app` | Cada producto agregado o eliminado (salir con `Ctrl + C`) |
| Últimas líneas | `docker compose logs --tail 20 app` | Solo las 20 líneas más recientes |
| Detener (sin borrar) | `docker compose stop` | `ps -a` los muestra como `Exited`; la página no carga |
| Volver a iniciar | `docker compose start` | Vuelven a `Up`; los datos siguen |
| Reiniciar | `docker compose restart` | Se detienen y arrancan de nuevo |
| Detener solo la BD | `docker compose stop db` | La página muestra "No hay conexion con la base de datos" |
| Iniciar solo la BD | `docker compose start db` | La app se recupera sola |
| Bajar y borrar contenedores (conserva datos) | `docker compose down` | Se borran contenedores y red; el volumen queda |
| Bajar y borrar también los datos | `docker compose down -v` | ⚠️ Borra el volumen `datos_inventario` |

Notas:
- La app tiene un *healthcheck* que llama a `/health`; esa ruta consulta la base de datos, así que `(healthy)` en la app demuestra que los dos contenedores se comunican por la red `red_inventario`.
- Ambos servicios tienen `restart: unless-stopped`: si un proceso falla, Docker lo vuelve a arrancar (pero respeta un `docker compose stop` hecho a mano).

## Probar la persistencia
1. Agregar un producto desde la página.
2. `docker compose down` (sin `-v`).
3. `docker compose up -d`.
4. Recargar la página: el producto sigue ahí porque está en el volumen `datos_inventario`.

## Arquitectura
- **app**: contenedor construido con el Dockerfile propio (Flask).
- **db**: contenedor PostgreSQL con el volumen `datos_inventario`.
- **red_inventario**: red de Docker; la app llega a la base de datos por el nombre `db`.
- Las credenciales se pasan por variables de entorno (`.env`, no se sube a GitHub).
