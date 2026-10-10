#!/usr/bin/env python3
"""
Robot de Resultados de Loterías F-26 (corre en GitHub Actions).

Busca los resultados en enloteria.com (y si falla, en loteriasdominicanashoy.com),
los verifica contra el historial guardado y actualiza:
  data/historial.json  -> todos los sorteos
  data/hoy.json        -> últimos 40 días (lo que la app consulta cada minuto)

Uso:
  python robot.py                 -> una pasada
  python robot.py --vigilar 40    -> repite cada minuto hasta 40 min mientras falten sorteos
                                     (hace git commit/push cada vez que entra algo nuevo)
  python robot.py --prueba        -> muestra lo que lee, sin guardar
"""
import json, os, re, sys, time, html, unicodedata, subprocess
import urllib.request
from datetime import datetime, timedelta, timezone

RD = timezone(timedelta(hours=-4))
BASE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(BASE, "data", "historial.json")
HOY = os.path.join(BASE, "data", "hoy.json")

# código, slug en enloteria.com, nombres en loteriasdominicanashoy.com, hora (h, m)
LOTERIAS = [
    ("lr",   "la-primera",       ["la primera dia", "la primera"],  (12, 0)),
    ("real", "real",             ["loteria real", "real"],          (12, 55)),
    ("gm",   "gana-mas",         ["gana mas"],                      (14, 30)),
    ("ny-t", "new-york-tarde",   ["new york tarde"],                (14, 30)),
    ("lrn",  "la-primera-noche", ["la primera noche"],              (19, 0)),
    ("lp",   "loteka",           ["loteka"],                        (19, 50)),
    ("ld",   "leidsa",           ["leidsa quiniela pale", "quiniela pale"], (20, 55)),
    ("nn",   "nacional-noche",   ["nacional noche"],                (21, 0)),
    ("ny-n", "new-york-noche",   ["new york noche"],                (22, 30)),
]
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
         "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}


def ahora():
    return datetime.now(RD)


REGISTRO = []


def log(msg):
    linea = f"[{ahora():%Y-%m-%d %I:%M %p}] {msg}"
    print(linea, flush=True)
    REGISTRO.append(linea)


def guardar_registro():
    ruta = os.path.join(BASE, "data", "registro.txt")
    try:
        viejo = open(ruta, encoding="utf-8").read().splitlines()
    except Exception:
        viejo = []
    open(ruta, "w", encoding="utf-8").write("\n".join((viejo + REGISTRO)[-400:]) + "\n")
    REGISTRO.clear()


def ny_invierno(d):
    y = d.year
    nov1 = datetime(y, 11, 1, tzinfo=RD)
    fin = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    mar1 = datetime(y, 3, 1, tzinfo=RD)
    ini = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)
    return d >= fin or d < ini


def hora_sorteo(cod, d):
    h, m = next(x[3] for x in LOTERIAS if x[0] == cod)
    if cod in ("ny-t", "ny-n") and ny_invierno(d):
        h += 1
    if cod == "ld" and d.weekday() == 6:
        h, m = 15, 55
    return d.replace(hour=h, minute=m, second=0, microsecond=0)


# ---------- datos ----------
def cargar():
    try:
        with open(HIST, encoding="utf-8") as f:
            j = json.load(f)
    except Exception:
        j = {"draws": []}
    return {(d["lot"], d["date"]): d["n"] for d in j.get("draws", [])}


def guardar(db):
    try:
        calcular_activos(db)
    except Exception as e:
        log(f"alarmas: error {e}")
    draws = [{"lot": k[0], "date": k[1], "n": v} for k, v in db.items()]
    draws.sort(key=lambda x: (x["date"], x["lot"]))
    ts = ahora().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    corte = (ahora() - timedelta(days=40)).strftime("%Y-%m-%d")
    for ruta, lista in ((HIST, draws), (HOY, [d for d in draws if d["date"] >= corte])):
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"actualizado": ts, "draws": lista}, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, ruta)


# ---------- Alarmas (versión para compartir) ----------
# Las rutas vienen del secreto ALARMAS de GitHub; aquí no se escribe ninguna.
# Solo se publica el número a vigilar, dónde y hasta cuándo (data/activos.json), nunca el origen.
GRUPOS = {"gn": ["gm", "nn"], "g4": ["gm", "nn", "ld", "real"]}
ACTIVOS = os.path.join(BASE, "data", "activos.json")


def _lots(x):
    return GRUPOS.get(x, [x])


def _minutos(cod, fecha):
    d = datetime.fromisoformat(fecha).replace(tzinfo=RD, hour=12)
    t = hora_sorteo(cod, d)
    return t.hour * 60 + t.minute


def calcular_activos(db):
    try:
        crudo = os.environ.get("ALARMAS", "")
        rutas = json.loads(crudo or "[]")
        log(f"alarmas: {len(rutas)} rutas cargadas" if rutas else "alarmas: el secreto ALARMAS está vacío o no existe")
    except Exception:
        log("ALARMAS: el secreto no es JSON válido")
        return
    hoy = ahora().strftime("%Y-%m-%d")
    out = []
    for r in rutas:
        try:
            o, n, dias = int(r["o"]), int(r["r"]), int(r.get("dias", 3))
            src, dst = _lots(r["src"]), _lots(r["dst"])
        except Exception:
            continue
        desde = (ahora() - timedelta(days=dias + 2)).strftime("%Y-%m-%d")
        por_dia = {}
        for (lot, f), nums in db.items():
            if lot in src and f >= desde and o in nums:
                if f not in por_dia or _minutos(lot, f) < _minutos(por_dia[f], f):
                    por_dia[f] = lot
        for f, lot in por_dia.items():
            hasta = (datetime.fromisoformat(f) + timedelta(days=dias)).strftime("%Y-%m-%d")
            hit = None
            for k in range(dias + 1):
                dd = (datetime.fromisoformat(f) + timedelta(days=k)).strftime("%Y-%m-%d")
                for tl in dst:
                    if k == 0 and (tl == lot or _minutos(tl, dd) <= _minutos(lot, f)):
                        continue
                    if n in db.get((tl, dd), []):
                        hit = {"lot": tl, "date": dd}
                        break
                if hit:
                    break
            if hit is None and hasta < hoy:
                continue
            import hashlib
            aid = hashlib.sha1(f"{f}|{n}|{','.join(dst)}|{dias}".encode()).hexdigest()[:10]
            item = {"id": aid, "n": n, "lots": dst, "hasta": hasta,
                    "estado": "cumplida" if hit else "activa"}
            if hit:
                item["cumplio"] = hit
            if hit and any(x["n"] == n and x.get("cumplio") == hit for x in out):
                continue
            if not any(x["id"] == aid for x in out):
                out.append(item)
    out.sort(key=lambda x: (x["estado"] != "activa", x["hasta"]))
    with open(ACTIVOS, "w", encoding="utf-8") as fh:
        json.dump({"actualizado": ahora().isoformat(timespec="seconds"), "activos": out}, fh, ensure_ascii=False, separators=(",", ":"))


# ---------- lectura ----------
def bajar(url):
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}t={int(time.time())}", headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Mobile Safari/537.36",
        "Accept-Language": "es-DO,es;q=0.9", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def a_texto(h):
    h = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = html.unescape(h)
    h = unicodedata.normalize("NFD", h)
    h = "".join(c for c in h if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", h)


# "lunes 05 de octubre, 2026 2:30pm 67 24 05"
RE_EN_FECHA = re.compile(r"\b(\d{1,2}) de (ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*,? (?:de )?(\d{4})")
RE_3NUM = re.compile(r"(?<![\d:])(\d{2}) (\d{2}) (\d{2})(?![\d:])")


def leer_enloteria(cod, slug, fecha):
    """Devuelve {fecha: [n1,n2,n3]} con todos los sorteos que muestra la página."""
    # La página sin fecha trae el resultado de hoy primero; la de fecha a veces se atrasa.
    out = {}
    for url in (f"https://enloteria.com/resultados-{slug}", f"https://enloteria.com/resultados-{slug}-{fecha}"):
        try:
            for f, n in _leer_pagina(cod, a_texto(bajar(url))).items():
                out.setdefault(f, n)
        except Exception as e:
            log(f"{cod}: {url} no respondió ({e})")
    if not out:
        raise RuntimeError("sin datos")
    return out


RE_EN_CORTA = re.compile(r"\b(?:lun|mar|mie|jue|vie|sab|dom)[a-z]*,? (ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*\.? (\d{1,2})(?:,? (\d{4}))?\b")


def _fecha_corta(m):
    hoy = ahora().date()
    mes, dia = MESES[m.group(1)], int(m.group(2))
    anio = int(m.group(3)) if m.group(3) else hoy.year
    try:
        f = datetime(anio, mes, dia).date()
    except ValueError:
        return None
    if not m.group(3) and f > hoy + timedelta(days=1):
        f = datetime(anio - 1, mes, dia).date()
    return f.strftime("%Y-%m-%d")


def _leer_pagina(cod, texto):
    """Formato actual: '2:30pm miercoles mie, oct 07 64 84 16'. También acepta el formato largo."""
    marcas = [(m, _fecha_corta(m)) for m in RE_EN_CORTA.finditer(texto)]
    if not marcas:
        marcas = [(m, f"{int(m.group(3)):04d}-{MESES[m.group(2)]:02d}-{int(m.group(1)):02d}") for m in RE_EN_FECHA.finditer(texto)]
    out = {}
    for i, (m, d) in enumerate(marcas):
        if not d:
            continue
        fin = marcas[i + 1][0].start() if i + 1 < len(marcas) else len(texto)
        tramo = texto[m.end(): min(fin, m.end() + 300)]
        if cod == "ld":
            k = tramo.find("quiniela pale")
            if k >= 0:
                tramo = tramo[k + len("quiniela pale"):]
            elif any(g in tramo for g in ("pega 3", "loto", "super kino", "super pale")):
                continue  # hay otros juegos y no se ve cuál es la Quiniela Palé: mejor no adivinar
        tramo = re.sub(r"\d{1,2}:\d{2} ?[ap]\.? ?m\.?", " ", tramo)
        n = RE_3NUM.match(tramo.strip()[:20]) if cod != "ld" else RE_3NUM.search(tramo[:80])
        if not n:
            continue
        if d not in out:
            out[d] = [int(x) for x in n.groups()]
    return out


# respaldo: portada de loteriasdominicanashoy.com (formato del f26.py de Termux)
RE_LD_FECHA = re.compile(r"\b(\d{1,2})[ \-/](ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z]*\.?,?[ \-/](\d{4})\b"
                         r"|\b(\d{1,2})[\-/](\d{1,2})[\-/](\d{4})\b")
RE_LD_NUM = re.compile(r"(?<!\d)(\d{2})[ \-–]*(\d{2})[ \-–]*(\d{2})(?!\d)")
CORTES = ["la primera", "loteria real", " real ", "gana mas", "new york", "loteka", "nacional", "leidsa",
          "lotedom", "king lottery", "la suerte", "florida", "anguila", "anguilla", "new jersey", "georgia",
          "haiti", "quiniela", "pega 3", "loto pool", "super kino", "resultados salen", "salen a las",
          "pendiente", "proximo sorteo", "en espera"]


def leer_portada():
    texto = a_texto(bajar("https://www.loteriasdominicanashoy.com/"))
    hallado, usados = {}, []
    for cod, _, nombres, _ in LOTERIAS:
        for nombre in nombres:
            for m in re.finditer(r"\b" + re.escape(nombre) + r"\b", texto):
                if any(a <= m.start() < b for a, b in usados):
                    continue
                v = texto[m.end(): m.end() + 200]
                fin = len(v)
                for c in CORTES:
                    k = v.find(c)
                    if 0 < k < fin and c.strip() not in nombre:
                        fin = k
                v = v[:fin]
                f = RE_LD_FECHA.search(v)
                if not f:
                    continue
                n = RE_LD_NUM.search(v[f.end(): f.end() + 30])
                if not n:
                    continue
                if f.group(1):
                    fecha = f"{int(f.group(3)):04d}-{MESES[f.group(2)]:02d}-{int(f.group(1)):02d}"
                else:
                    fecha = f"{int(f.group(6)):04d}-{int(f.group(5)):02d}-{int(f.group(4)):02d}"
                usados.append((m.start(), m.end()))
                if cod not in hallado or fecha > hallado[cod][0]:
                    hallado[cod] = (fecha, [int(x) for x in n.groups()])
            if cod in hallado:
                break
    vistos = {}
    for cod, v in hallado.items():
        vistos.setdefault((v[0], tuple(v[1])), []).append(cod)
    for cods in vistos.values():
        if len(cods) > 1:
            for c in cods:
                hallado.pop(c, None)
    return hallado


# ---------- lógica ----------
def valido(cod, fecha, nums, d):
    if not (len(nums) == 3 and all(0 <= x <= 99 for x in nums)):
        return False
    hoy = d.strftime("%Y-%m-%d")
    if fecha > hoy:
        return False
    if fecha == hoy and d < hora_sorteo(cod, d) + timedelta(minutes=2):
        return False  # todavía no ha sido el sorteo
    return True


def revisar(db, cods, d):
    """Busca resultados para las loterías indicadas. Devuelve lista de nuevos."""
    nuevos, hoy = [], d.strftime("%Y-%m-%d")
    faltan_portada = []
    for cod, slug, _, _ in LOTERIAS:
        if cod not in cods:
            continue
        try:
            pag = leer_enloteria(cod, slug, hoy)
        except Exception as e:
            log(f"{cod}: enloteria no respondió ({e})")
            faltan_portada.append(cod)
            continue
        log(f"{cod}: leído " + ", ".join(f"{f} {'-'.join(f'{x:02d}' for x in n)}" for f, n in sorted(pag.items())[-3:]))
        # verificación: lo que dice la página de días anteriores debe coincidir con lo guardado
        iguales = [f for f, n in pag.items() if db.get((cod, f)) == n]
        distintos = [f for f, n in pag.items() if (cod, f) in db and db[(cod, f)] != n]
        conocidos = len(iguales) + len(distintos)
        if distintos or (conocidos >= 1 and len(iguales) < min(3, conocidos)) or not pag:
            log(f"{cod}: lectura dudosa (iguales {len(iguales)}, distintos {distintos[:3]}); no se guarda")
            faltan_portada.append(cod)
            continue
        for f, n in sorted(pag.items()):
            if (cod, f) not in db and valido(cod, f, n, d) and f >= (d - timedelta(days=20)).strftime("%Y-%m-%d"):
                db[(cod, f)] = n
                nuevos.append((cod, f, n))
        if (cod, hoy) not in db and hora_sorteo(cod, d) <= d:
            faltan_portada.append(cod)
    # La portada de loteriasdominicanashoy.com ya no se usa para guardar: mezcla sorteos
    # parecidos (ej. Loteka y Loteka Tarde). Solo se anota en el registro para comparar.
    if faltan_portada:
        try:
            port = leer_portada()
            for cod in faltan_portada:
                if cod in port:
                    log(f"{cod}: la portada dice {port[cod]} (no se guarda; se espera a enloteria)")
        except Exception as e:
            log(f"portada no respondió ({e})")
    for cod, f, n in nuevos:
        log(f"NUEVO {cod} {f}: " + " - ".join(f"{x:02d}" for x in n))
    return nuevos


def pendientes(db, d, ventana=120):
    hoy = d.strftime("%Y-%m-%d")
    out = []
    for cod, *_ in LOTERIAS:
        t = hora_sorteo(cod, d)
        if t <= d <= t + timedelta(minutes=ventana) and (cod, hoy) not in db:
            out.append(cod)
    return out


def git_push(msg):
    guardar_registro()
    subprocess.run(["git", "add", "data"], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], check=True)
    for _ in range(3):
        if subprocess.run(["git", "push", "-q"]).returncode == 0:
            return
        subprocess.run(["git", "pull", "-q", "--rebase", "-X", "theirs"])
    log("no se pudo hacer push")


def main():
    args = sys.argv[1:]
    db = cargar()
    if "--prueba" in args:
        d = ahora()
        for cod, slug, _, _ in LOTERIAS:
            try:
                pag = leer_enloteria(cod, slug, d.strftime("%Y-%m-%d"))
                print(cod, sorted(pag.items())[-4:])
            except Exception as e:
                print(cod, "error", e)
        print("portada:", leer_portada())
        return
    if "--vigilar" in args:
        limite = time.time() + 60 * int(args[args.index("--vigilar") + 1])
        while True:
            d = ahora()
            pend = pendientes(db, d)
            if not pend:
                log("nada pendiente")
                break
            log("buscando: " + ", ".join(pend))
            nuevos = revisar(db, set(pend), d)
            if nuevos:
                guardar(db)
                git_push("Resultados " + ", ".join(f"{c} {f}" for c, f, _ in nuevos))
            if time.time() > limite:
                break
            time.sleep(60)
        git_push("Registro del robot")
        return
    # pasada completa (repaso): todas las loterías, rellena huecos de los últimos 20 días
    if "--prueba-log" in args:
        d = ahora()
        for cod, slug, _, _ in LOTERIAS:
            try:
                print(cod, sorted(leer_enloteria(cod, slug, d.strftime("%Y-%m-%d")).items())[-3:], flush=True)
            except Exception as e:
                print(cod, "error", e, flush=True)
    nuevos = revisar(db, {x[0] for x in LOTERIAS}, ahora())
    guardar(db)
    if "--push" in args:
        git_push("Repaso " + ahora().strftime("%Y-%m-%d %H:%M") + (f" (+{len(nuevos)})" if nuevos else ""))


if __name__ == "__main__":
    main()


