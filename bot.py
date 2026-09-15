"""
Bot de Telegram - Información y análisis de fútbol
(LaLiga, Premier, Serie A, Bundesliga, Primeira Liga)
--------------------------------------------------------------------------
Comandos:
  /partidos            -> partidos de hoy en las 5 ligas, marcando ⚡ los que
                           tienen gran diferencia de clasificación
  /partidos manana      -> lo mismo, para mañana
  /diferencia <id>      -> detalle de la diferencia de clasificación de un partido
  /cuotas <equipo>       -> compara cuotas 1X2 de varias casas para el próximo
                           partido de ese equipo
  /alineaciones <id>    -> alineación oficial (si el plan de datos la incluye)
  /lesiones <equipo>     -> bajas conocidas (requiere plan de pago, ver aviso)
  /seguir <id>           -> avisa en cuanto se publique la alineación oficial
  /ligas                 -> ligas que sigue el bot

Fuentes de datos:
  - Partidos y clasificación: football-data.org (plan gratuito)
  - Cuotas: the-odds-api.com (plan gratuito, 500 peticiones/mes)

NADA de esto usa datos en directo del partido ni fuentes con ventaja de
tiempo sobre las casas de apuestas: solo calendario, clasificación pública,
cuotas pre-partido publicadas por las propias casas, y alineaciones
oficiales ya confirmadas.
"""

import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

MADRID_TZ = ZoneInfo("Europe/Madrid")


def ahora_madrid():
    """Fecha/hora actual en la zona horaria de España, sin importar en qué
    zona horaria esté el servidor donde corre el bot."""
    return datetime.now(MADRID_TZ)


# ---------------------------------------------------------------------
# CONFIGURACIÓN — rellena estos tres valores (ver README.md)
# ---------------------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "PON_AQUI_TU_TOKEN")
FOOTBALL_DATA_KEY = os.environ.get("API_FOOTBALL_KEY", "PON_AQUI_TU_API_KEY")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "PON_AQUI_TU_ODDS_API_KEY")

FD_BASE = "https://api.football-data.org/v4"
FD_HEADERS = {"X-Auth-Token": FOOTBALL_DATA_KEY}

ODDS_BASE = "https://api.the-odds-api.com/v4"

# Códigos de competición en football-data.org
LIGAS = {
    "LaLiga": "PD",
    "Premier League": "PL",
    "Serie A": "SA",
    "Bundesliga": "BL1",
    "Primeira Liga": "PPL",
}

# Códigos de deporte/liga en The Odds API (para /cuotas)
ODDS_SPORT_KEYS = {
    "LaLiga": "soccer_spain_la_liga",
    "Premier League": "soccer_epl",
    "Serie A": "soccer_italy_serie_a",
    "Bundesliga": "soccer_germany_bundesliga",
    "Primeira Liga": "soccer_portugal_primeira_liga",
}

# Umbral de puestos de diferencia en la tabla para considerar un partido
# "con gran diferencia deportiva". Ajusta este número a tu gusto.
UMBRAL_DIFERENCIA = 8

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Partidos que el usuario quiere "seguir" para aviso de alineación:
# { fixture_id: {"chat_id": ..., "avisado": False} }
SEGUIMIENTOS = {}


# ---------------------------------------------------------------------
# FOOTBALL-DATA.ORG — partidos y clasificación
# ---------------------------------------------------------------------
def get_fixtures(date_str: str):
    """Devuelve la lista de partidos de las 5 ligas para una fecha dada."""
    partidos = []
    for nombre_liga, codigo in LIGAS.items():
        try:
            resp = requests.get(
                f"{FD_BASE}/competitions/{codigo}/matches",
                headers=FD_HEADERS,
                params={"dateFrom": date_str, "dateTo": date_str},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("matches", [])
            for p in data:
                partidos.append(
                    {
                        "id": p["id"],
                        "liga": nombre_liga,
                        "liga_codigo": codigo,
                        "hora": p["utcDate"],
                        "local": p["homeTeam"]["name"],
                        "visitante": p["awayTeam"]["name"],
                    }
                )
        except Exception as e:
            logger.warning(f"Error consultando partidos de {nombre_liga}: {e}")
    return partidos


def get_standings(codigo_liga: str):
    """Devuelve {nombre_equipo: posicion} para una liga."""
    try:
        resp = requests.get(
            f"{FD_BASE}/competitions/{codigo_liga}/standings", headers=FD_HEADERS, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        tabla = {}
        for grupo in data.get("standings", []):
            if grupo.get("type") != "TOTAL":
                continue
            for fila in grupo.get("table", []):
                tabla[fila["team"]["name"]] = fila["position"]
        return tabla
    except Exception as e:
        logger.warning(f"Error consultando clasificación de {codigo_liga}: {e}")
        return {}


def get_lineup(fixture_id: int):
    """El plan gratuito de football-data.org no siempre incluye alineaciones."""
    try:
        resp = requests.get(f"{FD_BASE}/matches/{fixture_id}", headers=FD_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        home_lineup = data.get("homeTeam", {}).get("lineup", [])
        away_lineup = data.get("awayTeam", {}).get("lineup", [])
        if not home_lineup and not away_lineup:
            return []
        return [
            {"team": data["homeTeam"], "lineup": home_lineup},
            {"team": data["awayTeam"], "lineup": away_lineup},
        ]
    except Exception as e:
        logger.warning(f"Error consultando alineaciones: {e}")
        return []


# ---------------------------------------------------------------------
# THE ODDS API — comparador de cuotas
# ---------------------------------------------------------------------
def get_odds_for_team(team_query: str):
    """Busca el próximo partido de un equipo (por nombre parcial) en
    cualquiera de las 5 ligas y devuelve las cuotas 1X2 de cada casa."""
    team_query_lower = team_query.lower()
    for nombre_liga, sport_key in ODDS_SPORT_KEYS.items():
        try:
            resp = requests.get(
                f"{ODDS_BASE}/sports/{sport_key}/odds",
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
                timeout=15,
            )
            resp.raise_for_status()
            eventos = resp.json()
        except Exception as e:
            logger.warning(f"Error consultando cuotas de {nombre_liga}: {e}")
            continue

        for ev in eventos:
            local = ev.get("home_team", "")
            visitante = ev.get("away_team", "")
            if team_query_lower in local.lower() or team_query_lower in visitante.lower():
                return nombre_liga, local, visitante, ev.get("bookmakers", [])
    return None, None, None, []


# ---------------------------------------------------------------------
# COMANDOS DEL BOT
# ---------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hola. Soy tu bot de análisis de fútbol.\n\n"
        "Comandos disponibles:\n"
        "/partidos - partidos de hoy (⚡ = gran diferencia de clasificación)\n"
        "/partidos manana - partidos de mañana\n"
        "/diferencia <id> - detalle de la diferencia de un partido\n"
        "/cuotas <equipo> - compara cuotas de varias casas\n"
        "/alineaciones <id> - alineación oficial si está disponible\n"
        "/lesiones <equipo> - bajas conocidas\n"
        "/seguir <id> - te aviso cuando salga la alineación oficial\n"
        "/ligas - ligas que sigo"
    )


async def ligas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = "🏆 Ligas que sigo:\n" + "\n".join(f"• {n}" for n in LIGAS)
    await update.message.reply_text(texto)


async def partidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dia = "manana" if context.args and context.args[0].lower() in ("manana", "mañana") else "hoy"
    fecha = ahora_madrid() + timedelta(days=1 if dia == "manana" else 0)
    fecha_str = fecha.strftime("%Y-%m-%d")

    await update.message.reply_text("🔎 Buscando partidos y comparando clasificaciones...")
    partidos_list = get_fixtures(fecha_str)

    if not partidos_list:
        await update.message.reply_text(f"No hay partidos de las 5 ligas el {fecha_str}.")
        return

    # Cachea la clasificación de cada liga para no pedirla partido a partido
    tablas_cache = {}
    for codigo in set(p["liga_codigo"] for p in partidos_list):
        tablas_cache[codigo] = get_standings(codigo)

    lineas = [f"⚽ Partidos del {fecha_str}:\n"]
    for p in partidos_list:
        hora_local = datetime.fromisoformat(p["hora"]).astimezone(MADRID_TZ).strftime("%H:%M")
        tabla = tablas_cache.get(p["liga_codigo"], {})
        pos_local = tabla.get(p["local"])
        pos_visit = tabla.get(p["visitante"])

        marca = ""
        detalle_pos = ""
        if pos_local and pos_visit:
            diff = abs(pos_local - pos_visit)
            detalle_pos = f" ({pos_local}º vs {pos_visit}º)"
            if diff >= UMBRAL_DIFERENCIA:
                marca = " ⚡"

        lineas.append(
            f"[{p['id']}] {hora_local} · {p['liga']}{marca}\n"
            f"{p['local']} vs {p['visitante']}{detalle_pos}\n"
        )
    lineas.append(
        "\n⚡ = diferencia de clasificación ≥ "
        f"{UMBRAL_DIFERENCIA} puestos.\n"
        "Usa /diferencia <id>, /cuotas <equipo>, /alineaciones <id> o /seguir <id>."
    )
    await update.message.reply_text("\n".join(lineas))


async def diferencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /diferencia <id_partido>  (usa /partidos para ver los IDs)")
        return
    fixture_id = int(context.args[0])

    try:
        resp = requests.get(f"{FD_BASE}/matches/{fixture_id}", headers=FD_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        await update.message.reply_text(f"No pude consultar ese partido: {e}")
        return

    codigo_liga = data.get("competition", {}).get("code")
    local = data["homeTeam"]["name"]
    visitante = data["awayTeam"]["name"]
    tabla = get_standings(codigo_liga) if codigo_liga else {}
    pos_local = tabla.get(local, "?")
    pos_visit = tabla.get(visitante, "?")

    texto = (
        f"📊 {local} vs {visitante}\n\n"
        f"{local}: {pos_local}º\n"
        f"{visitante}: {pos_visit}º\n"
    )
    if isinstance(pos_local, int) and isinstance(pos_visit, int):
        diff = abs(pos_local - pos_visit)
        texto += f"\nDiferencia: {diff} puestos"
        if diff >= UMBRAL_DIFERENCIA:
            texto += " ⚡ (gran diferencia deportiva)"
    await update.message.reply_text(texto)


async def cuotas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /cuotas <equipo>  (ej. /cuotas Elche)")
        return
    equipo = " ".join(context.args)
    await update.message.reply_text(f"🔎 Buscando cuotas para {equipo}...")

    liga, local, visitante, bookmakers = get_odds_for_team(equipo)
    if not bookmakers:
        await update.message.reply_text(
            "No encontré cuotas para ese equipo. Puede que no tenga partido "
            "próximo en las 5 ligas, o que el nombre no coincida — prueba con "
            "el nombre en inglés (ej. 'Real Madrid', 'Bayern Munich')."
        )
        return

    lineas = [f"💰 Cuotas {local} vs {visitante} ({liga}):\n"]
    mejor_local, mejor_empate, mejor_visit = 0, 0, 0
    for bk in bookmakers:
        nombre_casa = bk.get("title", "?")
        for market in bk.get("markets", []):
            if market["key"] != "h2h":
                continue
            precios = {o["name"]: o["price"] for o in market["outcomes"]}
            c_local = precios.get(local, "-")
            c_empate = precios.get("Draw", "-")
            c_visit = precios.get(visitante, "-")
            lineas.append(f"{nombre_casa}: 1={c_local}  X={c_empate}  2={c_visit}")
            if isinstance(c_local, (int, float)):
                mejor_local = max(mejor_local, c_local)
            if isinstance(c_empate, (int, float)):
                mejor_empate = max(mejor_empate, c_empate)
            if isinstance(c_visit, (int, float)):
                mejor_visit = max(mejor_visit, c_visit)

    lineas.append(
        f"\n🏆 Mejor cuota disponible: 1={mejor_local}  X={mejor_empate}  2={mejor_visit}"
    )
    await update.message.reply_text("\n".join(lineas))


async def alineaciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /alineaciones <id_partido>  (usa /partidos para ver los IDs)")
        return
    fixture_id = context.args[0]
    data = get_lineup(fixture_id)
    if not data:
        await update.message.reply_text(
            "Aún no hay alineación oficial publicada, o el plan gratuito de la "
            "API no incluye alineaciones para este partido."
        )
        return

    lineas = []
    for equipo in data:
        nombre = equipo["team"]["name"]
        titulares = ", ".join(j.get("name", "?") for j in equipo.get("lineup", []))
        lineas.append(f"🔹 {nombre}\n{titulares}\n")
    await update.message.reply_text("\n".join(lineas))


async def lesiones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ El plan gratuito de la API de datos que usa este bot no incluye "
        "un listado de lesiones. Para tenerlo habría que:\n"
        "1) contratar un plan de pago de una API que sí lo incluya, o\n"
        "2) añadir búsqueda de noticias (más lento, pero gratis).\n\n"
        "Dile a Claude si quieres que añadamos la opción 2."
    )


async def seguir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /seguir <id_partido>  (usa /partidos para ver los IDs)")
        return
    fixture_id = int(context.args[0])
    SEGUIMIENTOS[fixture_id] = {"chat_id": update.effective_chat.id, "avisado": False}
    await update.message.reply_text(
        f"✅ Te avisaré en este chat en cuanto se publique la alineación oficial del partido {fixture_id}."
    )


# ---------------------------------------------------------------------
# TAREA EN SEGUNDO PLANO: revisa cada 5 min si ya hay alineación
# de los partidos que el usuario está "siguiendo"
# ---------------------------------------------------------------------
async def revisar_seguimientos(context: ContextTypes.DEFAULT_TYPE):
    for fixture_id, info in list(SEGUIMIENTOS.items()):
        if info["avisado"]:
            continue
        data = get_lineup(fixture_id)
        if data:
            lineas = [f"📋 ¡Alineación oficial publicada! (partido {fixture_id})\n"]
            for equipo in data:
                nombre = equipo["team"]["name"]
                titulares = ", ".join(j.get("name", "?") for j in equipo.get("lineup", []))
                lineas.append(f"🔹 {nombre}\n{titulares}\n")
            await context.bot.send_message(chat_id=info["chat_id"], text="\n".join(lineas))
            info["avisado"] = True


# ---------------------------------------------------------------------
# ARRANQUE
# ---------------------------------------------------------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ligas", ligas))
    app.add_handler(CommandHandler("partidos", partidos))
    app.add_handler(CommandHandler("diferencia", diferencia))
    app.add_handler(CommandHandler("cuotas", cuotas))
    app.add_handler(CommandHandler("alineaciones", alineaciones))
    app.add_handler(CommandHandler("lesiones", lesiones))
    app.add_handler(CommandHandler("seguir", seguir))

    app.job_queue.run_repeating(revisar_seguimientos, interval=300, first=10)

    logger.info("Bot iniciado. Esperando comandos...")
    app.run_polling()


if __name__ == "__main__":
    main()
