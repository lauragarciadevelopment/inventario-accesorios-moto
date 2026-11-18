import os
import sys
import time
import signal
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify

app = Flask(__name__)

# Mensajes con fecha y hora; se ven con "docker compose logs app"
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("inventario")
# No mostrar en los logs las consultas automaticas del healthcheck (cada 10 s)
logging.getLogger("werkzeug").addFilter(lambda r: "/health" not in r.getMessage())

CATEGORIAS = ["Guantes", "Chaquetas", "Reflectivos", "Candados con alarma", "Guayas"]


def conectar():
    # Los datos de conexión vienen de variables de entorno (no están en el código)
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def ejecutar(sql, params=(), fetch=False):
    conn = conectar()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetch:
                return cur.fetchall()
    finally:
        conn.close()


def iniciar_db():
    # Reintenta porque la BD puede tardar unos segundos en arrancar
    host = os.environ.get("DB_HOST")
    for intento in range(1, 16):
        try:
            log.info("Conectando a la base de datos en el host '%s' (intento %d)...",
                     host, intento)
            ejecutar("""CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL,
                talla TEXT,
                precio NUMERIC(12,2) NOT NULL,
                stock INT NOT NULL DEFAULT 0)""")
            total = ejecutar("SELECT COUNT(*) AS n FROM productos", fetch=True)[0]["n"]
            log.info("Conexion OK. Tabla 'productos' lista con %d producto(s) guardados.",
                     total)
            return
        except psycopg2.OperationalError:
            log.warning("La base de datos aun no responde; reintento en 2 segundos.")
            time.sleep(2)
    raise RuntimeError("No se pudo conectar a la base de datos")


PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Inventario de accesorios para moto</title>
<style>
body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}
input,select{padding:.4rem;margin:.2rem}button{padding:.4rem .8rem}
table{border-collapse:collapse;width:100%;margin-top:1rem}
td,th{border:1px solid #ccc;padding:.4rem;text-align:left}
.bajo{background:#ffe0e0}
</style></head><body>
<h1>Inventario de accesorios para moto</h1>
<div>
<input id="nombre" placeholder="Nombre del producto">
<select id="categoria"></select>
<input id="talla" placeholder="Talla (opcional)" size="10">
<input id="precio" type="number" placeholder="Precio">
<input id="stock" type="number" placeholder="Stock">
<button onclick="agregar()">Agregar</button>
</div>
<div style="margin-top:1rem">Filtrar:
<select id="filtro" onchange="cargar()"><option value="">Todas</option></select>
<small>(filas en rojo: stock de 3 o menos)</small></div>
<p id="aviso" style="color:#b00;font-weight:bold"></p>
<table><thead><tr><th>ID</th><th>Producto</th><th>Categoría</th><th>Talla</th><th>Precio</th><th>Stock</th><th></th></tr></thead>
<tbody id="lista"></tbody></table>
<script>
async function categorias(){
  const cats=await (await fetch("/api/categorias")).json();
  for(const c of cats){
    for(const id of ["categoria","filtro"]){
      const o=document.createElement("option"); o.value=c; o.textContent=c;
      document.getElementById(id).appendChild(o);
    }
  }
}
async function cargar(){
  const f=document.getElementById("filtro").value;
  const url="/api/productos"+(f?"?categoria="+encodeURIComponent(f):"");
  const r=await fetch(url);
  const items=await r.json();
  const tb=document.getElementById("lista"); tb.innerHTML="";
  document.getElementById("aviso").textContent = r.ok ? "" : items.error;
  if(!r.ok) return;
  for(const p of items){
    const tr=document.createElement("tr");
    if(p.stock<=3) tr.className="bajo";
    for(const k of ["id","nombre","categoria","talla","precio","stock"]){
      const td=document.createElement("td"); td.textContent=p[k]??""; tr.appendChild(td);
    }
    const td=document.createElement("td"); const b=document.createElement("button");
    b.textContent="Eliminar"; b.onclick=()=>eliminar(p.id); td.appendChild(b); tr.appendChild(td);
    tb.appendChild(tr);
  }
}
async function agregar(){
  const d={};
  for(const i of ["nombre","categoria","talla","precio","stock"]) d[i]=document.getElementById(i).value;
  const r=await fetch("/api/productos",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(d)});
  if(!r.ok){ alert((await r.json()).error); return; }
  for(const i of ["nombre","talla","precio","stock"]) document.getElementById(i).value="";
  cargar();
}
async function eliminar(id){ await fetch("/api/productos/"+id,{method:"DELETE"}); cargar(); }
categorias().then(cargar);
</script></body></html>"""


@app.route("/")
def inicio():
    return PAGINA


@app.errorhandler(psycopg2.OperationalError)
def sin_base_de_datos(e):
    # Si el contenedor "db" esta detenido, la app no se cae: responde 503
    log.error("No hay conexion con la base de datos: %s", str(e).strip())
    return jsonify(error="No hay conexion con la base de datos"), 503


@app.route("/health")
def health():
    # Comprueba que la app y la base de datos se comunican por la red de Docker
    ejecutar("SELECT 1")
    return jsonify(estado="ok", base_de_datos="conectada")


@app.route("/api/categorias")
def categorias():
    return jsonify(CATEGORIAS)


@app.route("/api/productos", methods=["GET"])
def listar():
    cat = request.args.get("categoria")
    sql = ("SELECT id, nombre, categoria, talla, precio::float AS precio, stock "
           "FROM productos")
    params = ()
    if cat:
        sql += " WHERE categoria = %s"
        params = (cat,)
    return jsonify(ejecutar(sql + " ORDER BY id", params, fetch=True))


@app.route("/api/productos", methods=["POST"])
def crear():
    d = request.get_json(silent=True) or {}
    if not d.get("nombre"):
        return jsonify(error="El nombre es obligatorio"), 400
    if d.get("categoria") not in CATEGORIAS:
        return jsonify(error="Categoría no válida"), 400
    try:
        precio = float(d.get("precio"))
        stock = int(d.get("stock") or 0)
    except (TypeError, ValueError):
        return jsonify(error="Precio y stock deben ser números"), 400
    if precio < 0 or stock < 0:
        return jsonify(error="Precio y stock no pueden ser negativos"), 400
    ejecutar(
        "INSERT INTO productos (nombre, categoria, talla, precio, stock) "
        "VALUES (%s, %s, %s, %s, %s)",
        (d["nombre"], d["categoria"], d.get("talla") or None, precio, stock))
    log.info("Producto agregado: %s (%s), stock %d", d["nombre"], d["categoria"], stock)
    return jsonify(mensaje="Producto agregado"), 201


@app.route("/api/productos/<int:producto_id>", methods=["DELETE"])
def eliminar(producto_id):
    ejecutar("DELETE FROM productos WHERE id = %s", (producto_id,))
    log.info("Producto eliminado: id %d", producto_id)
    return jsonify(mensaje="Producto eliminado")


def apagar(signum, frame):
    # "docker stop" envia la senal SIGTERM al proceso principal del contenedor.
    # Si no la atendemos, Docker espera y lo mata con SIGKILL (codigo de salida 137).
    log.info("Senal SIGTERM recibida (docker stop): cerrando la app de forma ordenada.")
    sys.exit(0)


signal.signal(signal.SIGTERM, apagar)

iniciar_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
