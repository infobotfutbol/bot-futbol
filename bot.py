"""
Bot de Telegram - Información de fútbol (LaLiga, Premier, Serie A, Bundesliga)
--------------------------------------------------------------------------
Qué hace:
  /partidos      -> partidos de hoy en las 4 ligas
  /partidos manana -> partidos de mañana
  /alineaciones <id_partido> -> alineación oficial si ya está publicada
  /lesiones <equipo> -> bajas conocidas de un equipo
  /seguir <id_partido> -> te avisa automáticamente en cuanto se publique
                          la alineación oficial de ese partido
  /ligas         -> lista los IDs de las 4 ligas que sigue el bot

Fuente de datos: API-Football (https://www.api-football.com/) - tiene plan
gratuito (100 peticiones/día) suficiente para uso personal.

NADA de esto usa datos en directo del partido ni fuentes con ventaja de
tiempo sobre las casas de apuestas: solo calendario, alineaciones oficiales
publicadas y lesiones confirmadas por fuentes públicas.
"""

import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

MADRID_TZ = ZoneInfo("Europe/Madrid")


def ahora_madrid():
    """Fecha/hora actual en la zona horaria de España, sin importar
    en qué zona horaria esté el servidor donde corre el bot."""
    return datetime.now(MADRID_TZ)
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    JobQueue,
)

# ---------------------------------------------------------------------
# CONFIGURACIÓN — rellena estos dos valores (ver README.md paso 1 y 2)
# ---------------------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "PON_AQUI_TU_TOKEN")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "PON_AQUI_TU_API_KEY")

API_BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}

# IDs de liga en API-Football
LIGAS = {
    "LaLiga": 140,
    "Premier League": 39,
    "Serie A": 135,
    "Bundesliga": 78,
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Partidos que el usuario quiere "seguir" para aviso de alineación:
# { fixture_id: {"chat_id": ..., "avisado": False} }
SEGUIMIENTOS = {}


# ---------------------------------------------------------------------
# FUNCIONES AUXILIARES DE API-FOOTBALL
# ---------------------------------------------------------------------
def get_fixtures(date_str: str):
    """Devuelve la lista de partidos de las 4 ligas para una fecha dada."""
    partidos = []
    for nombre_liga, liga_id in LIGAS.items():
        try:
            resp = requests.get(
                f"{API_BASE}/fixtures",
                headers=HEADERS,
                params={"league": liga_id, "season": datetime.now().year, "date": date_str},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("response", [])
            for p in data:
                partidos.append(
                    {
                        "id": p["fixture"]["id"],
                        "liga": nombre_liga,
                        "hora": p["fixture"]["date"],
                        "local": p["teams"]["home"]["name"],
                        "visitante": p["teams"]["away"]["name"],
                    }
                )
        except Exception as e:
            logger.warning(f"Error consultando {nombre_liga}: {e}")
    return partidos


def get_lineup(fixture_id: int):
    try:
        resp = requests.get(
            f"{API_BASE}/fixtures/lineups",
            headers=HEADERS,
            params={"fixture": fixture_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("response", [])
    except Exception as e:
        logger.warning(f"Error consultando alineaciones: {e}")
        return []


def get_injuries(team_name: str):
    try:
        # Primero buscamos el ID del equipo por nombre
        resp = requests.get(
            f"{API_BASE}/teams", headers=HEADERS, params={"search": team_name}, timeout=15
        )
        resp.raise_for_status()
        teams = resp.json().get("response", [])
        if not teams:
            return None, []
        team_id = teams[0]["team"]["id"]
        team_full_name = teams[0]["team"]["name"]

        resp2 = requests.get(
            f"{API_BASE}/injuries",
            headers=HEADERS,
            params={"team": team_id, "season": datetime.now().year},
            timeout=15,
        )
        resp2.raise_for_status()
        return team_full_name, resp2.json().get("response", [])
    except Exception as e:
        logger.warning(f"Error consultando lesiones: {e}")
        return None, []


# ---------------------------------------------------------------------
# COMANDOS DEL BOT
# ---------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hola. Soy tu bot de información de fútbol.\n\n"
        "Comandos disponibles:\n"
        "/partidos - partidos de hoy\n"
        "/partidos manana - partidos de mañana\n"
        "/alineaciones <id> - alineación oficial de un partido\n"
        "/lesiones <equipo> - bajas confirmadas de un equipo\n"
        "/seguir <id> - te aviso en cuanto salga la alineación oficial\n"
        "/ligas - ligas que sigo"
    )


async def ligas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = "🏆 Ligas que sigo:\n" + "\n".join(f"• {n}" for n in LIGAS)
    await update.message.reply_text(texto)


async def partidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dia = "manana" if context.args and context.args[0].lower() in ("manana", "mañana") else "hoy"
    fecha = ahora_madrid() + timedelta(days=1 if dia == "manana" else 0)
    fecha_str = fecha.strftime("%Y-%m-%d")

    await update.message.reply_text("🔎 Buscando partidos...")
    partidos_list = get_fixtures(fecha_str)

    if not partidos_list:
        await update.message.reply_text(f"No hay partidos de las 4 ligas el {fecha_str}.")
        return

    lineas = [f"⚽ Partidos del {fecha_str}:\n"]
    for p in partidos_list:
        hora_local = datetime.fromisoformat(p["hora"]).astimezone(MADRID_TZ).strftime("%H:%M")
        lineas.append(f"[{p['id']}] {hora_local} · {p['liga']}\n{p['local']} vs {p['visitante']}\n")
    lineas.append("\nUsa /alineaciones <id> o /seguir <id> con el número entre corchetes.")
    await update.message.reply_text("\n".join(lineas))


async def alineaciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /alineaciones <id_partido>  (usa /partidos para ver los IDs)")
        return
    fixture_id = context.args[0]
    data = get_lineup(fixture_id)
    if not data:
        await update.message.reply_text("Aún no hay alineación oficial publicada para este partido.")
        return

    lineas = []
    for equipo in data:
        nombre = equipo["team"]["name"]
        formacion = equipo.get("formation", "?")
        titulares = ", ".join(j["player"]["name"] for j in equipo.get("startXI", []))
        lineas.append(f"🔹 {nombre} ({formacion})\n{titulares}\n")
    await update.message.reply_text("\n".join(lineas))


async def lesiones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /lesiones <nombre_equipo>  (ej. /lesiones Real Madrid)")
        return
    equipo_nombre = " ".join(context.args)
    nombre_completo, data = get_injuries(equipo_nombre)
    if not nombre_completo:
        await update.message.reply_text("No encontré ese equipo. Prueba con el nombre en inglés/oficial.")
        return
    if not data:
        await update.message.reply_text(f"No hay bajas registradas para {nombre_completo} ahora mismo.")
        return

    lineas = [f"🚑 Bajas de {nombre_completo}:\n"]
    for inj in data:
        jugador = inj["player"]["name"]
        motivo = inj["player"].get("reason", "Sin especificar")
        lineas.append(f"• {jugador} — {motivo}")
    await update.message.reply_text("\n".join(lineas))


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
                formacion = equipo.get("formation", "?")
                titulares = ", ".join(j["player"]["name"] for j in equipo.get("startXI", []))
                lineas.append(f"🔹 {nombre} ({formacion})\n{titulares}\n")
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
    app.add_handler(CommandHandler("alineaciones", alineaciones))
    app.add_handler(CommandHandler("lesiones", lesiones))
    app.add_handler(CommandHandler("seguir", seguir))

    # revisa seguimientos cada 5 minutos
    app.job_queue.run_repeating(revisar_seguimientos, interval=300, first=10)

    logger.info("Bot iniciado. Esperando comandos...")
    app.run_polling()


if __name__ == "__main__":
    main()
