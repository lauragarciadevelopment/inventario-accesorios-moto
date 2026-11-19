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

# Dos modos con la MISMA imagen:
# - Sin la variable DB_HOST  -> modo memoria (Entrega 1: solo "docker run", sin base de datos).
#   Los datos se pierden al borrar el contenedor.
# - Con DB_HOST (compose.yaml) -> modo PostgreSQL (Entrega 2: datos en el volumen).
MODO_MEMORIA = not os.environ.get("DB_HOST")
memoria = []          # lista de productos cuando no hay base de datos
siguiente_id = 1


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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motoaccesorios · Inventario</title>
<link rel="icon" href="/static/logo.png">
<style>
:root{--oscuro:#0e0e11;--naranja:#ff6a1a;--naranja2:#e8197d;--degradado:linear-gradient(90deg,#ff7a18,#ff3d5a 55%,#e8197d);--fondo:#f3f4f6;--borde:#e2e5ea;--texto:#1f2933}
*{box-sizing:border-box}
body{margin:0;font-family:"Segoe UI",Roboto,Arial,sans-serif;background:var(--fondo);color:var(--texto)}
header{background:var(--oscuro);color:#fff;border-bottom:4px solid transparent;border-image:var(--degradado) 1}
.barra{max-width:1000px;margin:auto;padding:1rem 1.25rem;display:flex;align-items:center;gap:.9rem}
.logo{width:88px;height:88px;flex:none;border-radius:50%;padding:2px;background:var(--degradado)}
.barra h1{margin:0;font-size:1.45rem;letter-spacing:.3px}
.barra p{margin:.15rem 0 0;color:#aab2bd;font-size:.9rem}
.modo{margin-left:auto;font-size:.8rem;padding:.3rem .7rem;border-radius:999px;border:1px solid #ff6a1a;color:#ffb48a;white-space:nowrap}
main{max-width:1000px;margin:1.25rem auto;padding:0 1.25rem}
.tarjeta{background:#fff;border:1px solid var(--borde);border-radius:10px;padding:1rem 1.1rem;margin-bottom:1rem;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.tarjeta h2{margin:0 0 .7rem;font-size:1rem;color:var(--oscuro)}
.form{display:flex;flex-wrap:wrap;gap:.5rem}
input,select{min-width:0;padding:.55rem .65rem;border:1px solid #cfd4db;border-radius:6px;font-size:.95rem;background:#fff}
input:focus,select:focus{outline:2px solid var(--naranja);border-color:var(--naranja)}
#nombre{flex:2 1 180px}#categoria{flex:1 1 150px}#talla{flex:0 1 115px}#precio,#stock{flex:0 1 105px}
button{cursor:pointer;border:0;border-radius:6px;padding:.55rem 1.1rem;font-size:.95rem;font-weight:600}
.principal{background:var(--degradado);color:#fff}.principal:hover{filter:brightness(1.08)}
.eliminar{background:transparent;color:#b42318;border:1px solid #f1b8b2;padding:.35rem .7rem;font-weight:500}
.eliminar:hover{background:#fdecea}
.resumen{display:flex;flex-wrap:wrap;gap:.75rem;margin-bottom:1rem}
.dato{flex:1 1 160px;background:#fff;border:1px solid var(--borde);border-left:5px solid var(--naranja);border-radius:8px;padding:.6rem .9rem}
.dato.alerta{border-left-color:#d92d20}
.dato b{display:block;font-size:1.5rem}.dato span{color:#5f6b7a;font-size:.85rem}
.filtro{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap}
.filtro small{color:#5f6b7a}
table{border-collapse:collapse;width:100%;margin-top:.8rem;font-size:.95rem}
th{background:var(--oscuro);color:#fff;text-align:left;padding:.6rem;font-weight:600}
td{padding:.55rem .6rem;border-bottom:1px solid var(--borde)}
tbody tr:hover{background:#fafafa}
tr.bajo td{background:#fdecea}
.etiqueta{display:inline-block;padding:.15rem .55rem;border-radius:999px;font-size:.8rem;font-weight:600;color:#fff}
.poco{display:inline-block;margin-left:.4rem;padding:.1rem .45rem;border-radius:4px;background:#d92d20;color:#fff;font-size:.72rem;font-weight:700}
.num{text-align:right}
#aviso{color:#b42318;font-weight:600;margin:.6rem 0 0}
footer{text-align:center;color:#8a94a3;font-size:.8rem;margin:1.5rem 0}
</style></head><body>
<header><div class="barra">
<img class="logo" src="/static/logo.png" alt="Logo motoaccesorios">
<div><h1>Inventario de accesorios para moto</h1>
<p>Guantes · Chaquetas · Reflectivos · Candados con alarma · Guayas</p></div>
<span class="modo">MODO_TEXTO</span>
</div></header>
<main>
<div class="resumen">
<div class="dato"><b id="totalProductos">0</b><span>productos registrados</span></div>
<div class="dato"><b id="totalUnidades">0</b><span>unidades en stock</span></div>
<div class="dato alerta"><b id="totalBajo">0</b><span>con stock bajo (3 o menos)</span></div>
</div>
<div class="tarjeta"><h2>Agregar producto</h2>
<div class="form">
<input id="nombre" placeholder="Nombre del producto">
<select id="categoria"></select>
<input id="talla" placeholder="Talla">
<input id="precio" type="number" min="0" placeholder="Precio">
<input id="stock" type="number" min="0" placeholder="Stock">
<button class="principal" onclick="agregar()">Agregar</button>
</div></div>
<div class="tarjeta">
<div class="filtro"><h2 style="margin:0">Inventario</h2>
<select id="filtro" onchange="cargar()"><option value="">Todas las categorías</option></select>
<small>Filas en rojo: stock de 3 o menos</small></div>
<p id="aviso"></p>
<table><thead><tr><th>ID</th><th>Producto</th><th>Categoría</th><th>Talla</th><th class="num">Precio</th><th class="num">Stock</th><th></th></tr></thead>
<tbody id="lista"></tbody></table>
</div>
</main>
<footer>motoaccesorios_med · Proyecto Sistemas Operativos · Flask + PostgreSQL con Docker Compose</footer>
<script>
const COLORES={"Guantes":"#2563eb","Chaquetas":"#7c3aed","Reflectivos":"#ca8a04","Candados con alarma":"#059669","Guayas":"#475569"};
const pesos=new Intl.NumberFormat("es-CO",{style:"currency",currency:"COP",maximumFractionDigits:0});
async function categorias(){
  const cats=await (await fetch("/api/categorias")).json();
  for(const c of cats){
    for(const id of ["categoria","filtro"]){
      const o=document.createElement("option"); o.value=c; o.textContent=c;
      document.getElementById(id).appendChild(o);
    }
  }
}
function celda(tr,texto,clase){const td=document.createElement("td"); td.textContent=texto??""; if(clase) td.className=clase; tr.appendChild(td); return td;}
async function cargar(){
  const f=document.getElementById("filtro").value;
  const url="/api/productos"+(f?"?categoria="+encodeURIComponent(f):"");
  const r=await fetch(url);
  const items=await r.json();
  const tb=document.getElementById("lista"); tb.innerHTML="";
  document.getElementById("aviso").textContent = r.ok ? "" : items.error;
  if(!r.ok) return;
  let unidades=0, bajos=0;
  for(const p of items){
    unidades+=p.stock; if(p.stock<=3) bajos++;
    const tr=document.createElement("tr");
    if(p.stock<=3) tr.className="bajo";
    celda(tr,p.id); celda(tr,p.nombre);
    const tc=celda(tr,""); const e=document.createElement("span");
    e.className="etiqueta"; e.style.background=COLORES[p.categoria]||"#475569"; e.textContent=p.categoria; tc.appendChild(e);
    celda(tr,p.talla); celda(tr,pesos.format(p.precio),"num");
    const ts=celda(tr,p.stock,"num");
    if(p.stock<=3){const b=document.createElement("span"); b.className="poco"; b.textContent="POCO"; ts.appendChild(b);}
    const td=document.createElement("td"); const b=document.createElement("button");
    b.className="eliminar"; b.textContent="Eliminar"; b.onclick=()=>eliminar(p.id); td.appendChild(b); tr.appendChild(td);
    tb.appendChild(tr);
  }
  document.getElementById("totalProductos").textContent=items.length;
  document.getElementById("totalUnidades").textContent=unidades;
  document.getElementById("totalBajo").textContent=bajos;
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
    modo = ("Modo memoria (sin base de datos)" if MODO_MEMORIA
            else "Modo PostgreSQL (datos en volumen)")
    return PAGINA.replace("MODO_TEXTO", modo)


@app.errorhandler(psycopg2.OperationalError)
def sin_base_de_datos(e):
    # Si el contenedor "db" esta detenido, la app no se cae: responde 503
    log.error("No hay conexion con la base de datos: %s", str(e).strip())
    return jsonify(error="No hay conexion con la base de datos"), 503


@app.route("/health")
def health():
    if MODO_MEMORIA:
        return jsonify(estado="ok", base_de_datos="no usa (modo memoria)")
    # Comprueba que la app y la base de datos se comunican por la red de Docker
    ejecutar("SELECT 1")
    return jsonify(estado="ok", base_de_datos="conectada")


@app.route("/api/categorias")
def categorias():
    return jsonify(CATEGORIAS)


@app.route("/api/productos", methods=["GET"])
def listar():
    cat = request.args.get("categoria")
    if MODO_MEMORIA:
        return jsonify([p for p in memoria if not cat or p["categoria"] == cat])
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
    global siguiente_id
    if MODO_MEMORIA:
        memoria.append({"id": siguiente_id, "nombre": d["nombre"], "categoria": d["categoria"],
                        "talla": d.get("talla") or None, "precio": precio, "stock": stock})
        siguiente_id += 1
    else:
        ejecutar(
            "INSERT INTO productos (nombre, categoria, talla, precio, stock) "
            "VALUES (%s, %s, %s, %s, %s)",
            (d["nombre"], d["categoria"], d.get("talla") or None, precio, stock))
    log.info("Producto agregado: %s (%s), stock %d", d["nombre"], d["categoria"], stock)
    return jsonify(mensaje="Producto agregado"), 201


@app.route("/api/productos/<int:producto_id>", methods=["DELETE"])
def eliminar(producto_id):
    if MODO_MEMORIA:
        memoria[:] = [p for p in memoria if p["id"] != producto_id]
    else:
        ejecutar("DELETE FROM productos WHERE id = %s", (producto_id,))
    log.info("Producto eliminado: id %d", producto_id)
    return jsonify(mensaje="Producto eliminado")


def apagar(signum, frame):
    # "docker stop" envia la senal SIGTERM al proceso principal del contenedor.
    # Si no la atendemos, Docker espera y lo mata con SIGKILL (codigo de salida 137).
    log.info("Senal SIGTERM recibida (docker stop): cerrando la app de forma ordenada.")
    sys.exit(0)


signal.signal(signal.SIGTERM, apagar)

if MODO_MEMORIA:
    log.info("No hay variable DB_HOST: modo memoria (sin base de datos).")
else:
    iniciar_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
