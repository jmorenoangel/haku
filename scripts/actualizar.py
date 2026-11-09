#!/usr/bin/env python3
"""Trae la pauta de Meta Ads, la agrupa por sociedad / zona / canal y genera
el informe en salida/sitio/index.html.

Uso:
  META_TOKEN=... [INFORME_PIN=...] python scripts/actualizar.py
  python scripts/actualizar.py --demo   # datos inventados, sin Meta
"""
import base64
import csv
import datetime as dt
import gzip
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config"
SALIDA = RAIZ / "salida"
ITERACIONES = 310_000
BOGOTA = dt.timezone(dt.timedelta(hours=-5))
TIPOS_LEAD = ["lead", "onsite_conversion.lead_grouped", "leadgen_grouped",
              "offsite_conversion.fb_pixel_lead"]


def avisar(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- Meta API
def pedir(url, intentos=6):
    for n in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(cuerpo).get("error", {})
            except ValueError:
                err = {}
            codigo = err.get("code")
            # Límites de uso o errores temporales: esperar y reintentar.
            if codigo in (1, 2, 4, 17, 80000, 80004, 613) or e.code >= 500:
                espera = 30 * (n + 1)
                avisar(f"  Meta pidió esperar ({codigo}); reintento en {espera}s")
                time.sleep(espera)
                continue
            mensaje = err.get("message", cuerpo[:300])
            if codigo == 190:
                mensaje += " — el token no es válido o fue revocado."
            raise SystemExit(f"Error de Meta ({codigo}): {mensaje}")
        except urllib.error.URLError as e:
            avisar(f"  Sin conexión con Meta ({e.reason}); reintento")
            time.sleep(15 * (n + 1))
    raise SystemExit("Meta no respondió después de varios intentos.")


def leads_de(acciones):
    if not acciones:
        return 0
    por_tipo = {a.get("action_type"): float(a.get("value", 0)) for a in acciones}
    for tipo in TIPOS_LEAD:
        if tipo in por_tipo:
            return int(round(por_tipo[tipo]))
    return 0


def tramos_mensuales(desde, hasta):
    inicio = desde
    while inicio <= hasta:
        siguiente = (inicio.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        fin = min(siguiente - dt.timedelta(days=1), hasta)
        yield inicio, fin
        inicio = fin + dt.timedelta(days=1)


def traer_meta(cfg, token, hasta):
    version = cfg.get("version_api", "v23.0")
    base = f"https://graph.facebook.com/{version}"
    desde = dt.date.fromisoformat(cfg["desde"])
    filas, moneda = [], None
    campos = ("account_id,account_name,campaign_id,campaign_name,adset_id,adset_name,"
              "spend,impressions,reach,clicks,actions")
    for cuenta in cfg["cuentas"]:
        cuenta = str(cuenta).replace("act_", "").strip()
        info = pedir(f"{base}/act_{cuenta}?" + urllib.parse.urlencode(
            {"fields": "name,currency", "access_token": token}))
        moneda = moneda or info.get("currency")
        avisar(f"Cuenta {info.get('name', cuenta)} ({cuenta})")
        for ini, fin in tramos_mensuales(desde, hasta):
            params = {
                "level": "adset",
                "time_increment": 1,
                "time_range": json.dumps({"since": ini.isoformat(), "until": fin.isoformat()}),
                "fields": campos,
                "use_unified_attribution_setting": "true",
                "limit": 500,
                "access_token": token,
            }
            url = f"{base}/act_{cuenta}/insights?" + urllib.parse.urlencode(params)
            n = 0
            while url:
                resp = pedir(url)
                for r in resp.get("data", []):
                    filas.append({
                        "fecha": r["date_start"],
                        "cuenta": r.get("account_name", cuenta),
                        "campana": r.get("campaign_name", ""),
                        "conjunto_id": r.get("adset_id", ""),
                        "conjunto": r.get("adset_name", ""),
                        "gasto": float(r.get("spend", 0) or 0),
                        "impresiones": int(r.get("impressions", 0) or 0),
                        "alcance": int(r.get("reach", 0) or 0),
                        "clics": int(r.get("clicks", 0) or 0),
                        "leads": leads_de(r.get("actions")),
                    })
                    n += 1
                url = resp.get("paging", {}).get("next")
            avisar(f"  {ini:%b %Y}: {n} filas")
    return filas, moneda or "COP"


# ---------------------------------------------------------------- Demo
def datos_demo(hasta):
    rnd = random.Random(7)
    zonas = {
        "Credimotos": ["Antioquia", "Bogota", "Llanos", "Villavicencio", "Uraba"],
        "Motos de los Andes": ["Bello", "BogotaCentro", "Envigado", "Llanos", "Meissen"],
        "Sabanamotos": ["BogotaCentro", "Funza", "Llanos", "SanJose"],
        "Motomovil": ["Bogota", "Bogota40km", "Melgar", "Meta"],
        "Todomovil": ["Apartado", "Caucasia", "Monteria", "Turbo"],
        "Motos del Atlantico": ["Cienaga", "Fundacion", "Valledupar"],
        "Centromotos": ["Bogota", "Bogota40km", "Cundinamarca"],
        "Motocredito": ["Antioquia", "Uraba"],
    }
    filas = []
    dia = dt.date(hasta.year, 1, 1)
    while dia <= hasta:
        for soc, zs in zonas.items():
            for z in zs:
                for canal in ("Call", "Sala"):
                    if canal == "Sala" and rnd.random() < 0.6:
                        continue
                    gasto = rnd.uniform(15000, 90000) * (0.4 if canal == "Sala" else 1)
                    cpl = rnd.uniform(900, 4500)
                    imp = int(gasto / rnd.uniform(9, 16))
                    clics = int(imp * rnd.uniform(0.01, 0.04))
                    filas.append({
                        "fecha": dia.isoformat(),
                        "cuenta": "Hakucreativo anuncios (demo)",
                        "campana": f"{soc} {'SALA' if canal == 'Sala' else 'CALL'}",
                        "conjunto_id": f"{soc}-{z}-{canal}",
                        "conjunto": f"META_PF_{z}_{soc.replace(' ', '')}",
                        "gasto": round(gasto, 2),
                        "impresiones": imp,
                        "alcance": int(imp / rnd.uniform(1.1, 1.5)),
                        "clics": clics,
                        "leads": int(gasto / cpl),
                    })
        dia += dt.timedelta(days=1)
    return filas, "COP"


# ---------------------------------------------------------------- Reglas
def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return t


def fichas(texto):
    return [f for f in re.split(r"[^a-z0-9]+", normalizar(texto)) if f]


def coincide(patron, junto, palabras):
    p = re.sub(r"[^a-z0-9]", "", normalizar(patron))
    return p in junto if len(p) >= 8 else p in palabras


def clasificador(reglas, asignaciones):
    def clasificar(campana, conjunto, conjunto_id):
        texto = f"{campana} {conjunto}"
        palabras = fichas(texto)
        junto = "".join(palabras)
        sociedad, alias = "Sin asignar", set()
        for s in reglas["sociedades"]:
            if any(coincide(p, junto, palabras) for p in s["patrones"]):
                sociedad = s["nombre"]
                alias = {w for p in s["patrones"] for w in fichas(p)} | set(fichas(s["nombre"]))
                break
        canal = reglas.get("canal_por_defecto", "Call")
        for c in reglas.get("canales", []):
            if any(coincide(p, junto, palabras) for p in c["patrones"]):
                canal = c["nombre"]
                break
        ignorar = set(reglas.get("palabras_ignoradas_en_zona", [])) | alias
        partes = [p for p in re.split(r"[_|\-–/]+", conjunto or "") if p.strip()]
        zona = next((p.strip() for p in partes
                     if not set(fichas(p)) <= ignorar and not p.strip().isdigit()), conjunto or "General")
        fijo = asignaciones.get(conjunto_id, {})
        return (fijo.get("sociedad") or sociedad, fijo.get("zona") or zona, fijo.get("canal") or canal)
    return clasificar


def leer_asignaciones():
    ruta = CONFIG / "asignaciones.csv"
    if not ruta.exists():
        return {}
    with ruta.open(encoding="utf-8-sig") as f:
        return {r["conjunto_id"].strip(): {k: (v or "").strip() for k, v in r.items()}
                for r in csv.DictReader(f) if r.get("conjunto_id")}


# ---------------------------------------------------------------- Armado
def armar(filas, moneda, hasta, clasificar):
    fechas = sorted({f["fecha"] for f in filas})
    idx_fecha = {d: i for i, d in enumerate(fechas)}
    conjuntos, idx_conj = [], {}
    cols = {k: [] for k in ("f", "j", "g", "im", "al", "cl", "l")}
    for f in filas:
        clave = f["conjunto_id"] or f["conjunto"]
        if clave not in idx_conj:
            soc, zona, canal = clasificar(f["campana"], f["conjunto"], clave)
            idx_conj[clave] = len(conjuntos)
            conjuntos.append({"i": clave, "n": f["conjunto"], "c": f["campana"],
                              "a": f["cuenta"], "s": soc, "z": zona, "k": canal})
        cols["f"].append(idx_fecha[f["fecha"]])
        cols["j"].append(idx_conj[clave])
        cols["g"].append(round(f["gasto"], 2))
        cols["im"].append(f["impresiones"])
        cols["al"].append(f["alcance"])
        cols["cl"].append(f["clics"])
        cols["l"].append(f["leads"])
    return {
        "generado": dt.datetime.now(BOGOTA).isoformat(timespec="minutes"),
        "hasta": hasta.isoformat(),
        "moneda": moneda,
        "fechas": fechas,
        "conjuntos": conjuntos,
        "d": cols,
    }


def cifrar(datos, pin):
    sal, iv = os.urandom(16), os.urandom(12)
    clave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal,
                       iterations=ITERACIONES).derive(pin.encode("utf-8"))
    crudo = gzip.compress(json.dumps(datos, separators=(",", ":")).encode("utf-8"))
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "it": ITERACIONES, "sal": b64(sal), "iv": b64(iv),
            "c": b64(AESGCM(clave).encrypt(iv, crudo, None))}


def main():
    demo = "--demo" in sys.argv
    # Sin INFORME_PIN el informe abre directo; con INFORME_PIN se cifra.
    pin = os.environ.get("INFORME_PIN", "").strip()
    cfg = json.loads((CONFIG / "cuentas.json").read_text(encoding="utf-8"))
    reglas = json.loads((CONFIG / "reglas.json").read_text(encoding="utf-8"))
    hasta = dt.datetime.now(BOGOTA).date() - dt.timedelta(days=1)

    if demo:
        filas, moneda = datos_demo(hasta)
    else:
        token = os.environ.get("META_TOKEN", "").strip()
        if not token:
            raise SystemExit("Falta META_TOKEN.")
        filas, moneda = traer_meta(cfg, token, hasta)
    if not filas:
        raise SystemExit("Meta no devolvió datos. Revisa que el usuario del sistema "
                         "tenga acceso a las cuentas publicitarias.")

    datos = armar(filas, moneda, hasta, clasificador(reglas, leer_asignaciones()))
    avisar(f"{len(filas)} filas · {len(datos['conjuntos'])} conjuntos · hasta {hasta}")

    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "sitio").mkdir(exist_ok=True)
    plantilla = (RAIZ / "web" / "plantilla.html").read_text(encoding="utf-8")
    contenido = cifrar(datos, pin) if pin else {"plano": datos}
    html = plantilla.replace("/*__DATOS__*/null",
                             json.dumps(contenido, separators=(",", ":")).replace("</", "<\\/"))
    (SALIDA / "sitio" / "index.html").write_text(html, encoding="utf-8")
    (SALIDA / "sitio" / ".nojekyll").write_text("")

    # Lista de control (no se publica): cómo quedó repartido cada conjunto.
    with (SALIDA / "conjuntos.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["conjunto_id", "sociedad", "zona", "canal", "conjunto", "campana", "cuenta"])
        for c in sorted(datos["conjuntos"], key=lambda c: (c["s"], c["z"], c["k"])):
            w.writerow([c["i"], c["s"], c["z"], c["k"], c["n"], c["c"], c["a"]])
    sin = sum(1 for c in datos["conjuntos"] if c["s"] == "Sin asignar")
    if sin:
        avisar(f"Ojo: {sin} conjuntos quedaron 'Sin asignar'. Revisa salida/conjuntos.csv")
    avisar("Listo: salida/sitio/index.html")


if __name__ == "__main__":
    main()
