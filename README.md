# Manual — Bot de fútbol para Telegram

Sigue estos pasos en orden. No necesitas saber programar, solo copiar y pegar.

---

## PASO 1 — Crear el bot en Telegram (2 minutos)

1. Abre Telegram y busca el usuario **@BotFather** (tiene una marca de verificación azul).
2. Escríbele `/newbot`.
3. Te pedirá un **nombre** (el que verás tú, ej. "Mi Bot de Fútbol") y un **usuario**
   que debe terminar en `bot` (ej. `mifutbolbot`).
4. BotFather te devuelve un mensaje con un **token**, algo así:
   `123456789:AAHk3jf9dKs...` — **guárdalo**, es la clave de tu bot.

---

## PASO 2 — Conseguir acceso a los datos de fútbol (gratis)

1. Ve a **https://www.api-football.com/** y crea una cuenta gratuita
   (plan "Free", 100 peticiones al día — de sobra para uso personal).
2. En tu panel (dashboard) verás una **API Key** — cópiala.

---

## PASO 3 — Configurar tus dos claves

Abre el archivo `bot.py` y sustituye estas dos líneas por tus datos reales:

```python
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "PON_AQUI_TU_TOKEN")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "PON_AQUI_TU_API_KEY")
```

Cambia `"PON_AQUI_TU_TOKEN"` por el token de BotFather, y
`"PON_AQUI_TU_API_KEY"` por tu clave de API-Football.

(Más adelante, en el Paso 5, verás una forma más segura de hacer esto
sin escribir las claves directamente en el archivo.)

---

## PASO 4 — Probarlo en tu propio ordenador (opcional pero recomendado)

Si tienes Python instalado:

```bash
pip install -r requirements.txt
python bot.py
```

Abre Telegram, busca tu bot por el usuario que le diste, y escríbele `/start`.
Si responde, funciona. Puedes cerrarlo con Ctrl+C — pero recuerda que así
solo funciona mientras tu ordenador esté encendido y el programa corriendo.

---

## PASO 5 — Dejarlo funcionando 24/7 (sin tu ordenador encendido)

Para que el bot funcione siempre, necesita estar en un servidor. La opción
más sencilla y gratuita para empezar es **Railway** (railway.app):

1. Crea una cuenta en **https://railway.app** (puedes entrar con GitHub).
2. Sube esta carpeta (`bot.py`, `requirements.txt`) a un repositorio de
   GitHub. Si no sabes cómo, la forma más fácil es:
   - Crea una cuenta en **https://github.com** si no tienes.
   - Crea un repositorio nuevo (botón verde "New").
   - Usa la opción "uploading an existing file" y arrastra los dos archivos.
3. En Railway, pulsa "New Project" → "Deploy from GitHub repo" → elige
   el repositorio que acabas de crear.
4. Railway detectará que es un proyecto Python. Antes de que arranque, ve a
   la pestaña **Variables** y añade:
   - `TELEGRAM_TOKEN` = tu token de BotFather
   - `API_FOOTBALL_KEY` = tu clave de API-Football

   (Esto es más seguro que escribirlas directamente en el código — el bot
   ya está preparado para leerlas de ahí automáticamente.)
5. Railway instalará las dependencias y arrancará `bot.py` solo. En unos
   minutos tu bot responderá 24/7, sin depender de tu ordenador.

El plan gratuito de Railway da varias horas de uso al mes, suficiente para
un bot personal ligero como este.

---

## Comandos disponibles

| Comando | Qué hace |
|---|---|
| `/partidos` | Partidos de hoy en LaLiga, Premier, Serie A y Bundesliga |
| `/partidos manana` | Partidos de mañana |
| `/alineaciones <id>` | Alineación oficial de un partido (usa el ID que te da `/partidos`) |
| `/lesiones <equipo>` | Bajas confirmadas de un equipo (ej. `/lesiones Real Madrid`) |
| `/seguir <id>` | El bot te avisa automáticamente en cuanto salga la alineación oficial |
| `/ligas` | Lista las ligas que sigue el bot |

---

## Qué NO hace este bot (y por qué)

No usa datos en directo del partido ni fuentes con ventaja de tiempo sobre
las cuotas de las casas de apuestas. Solo trabaja con:
- Calendario público de partidos
- Alineaciones oficiales ya publicadas
- Lesiones confirmadas por fuentes oficiales/prensa

Esto es intencional: cualquier sistema que capte eventos en directo
(lesiones durante el partido, asistencias médicas, etc.) antes de que la
casa de apuestas actualice su cuota incumple los términos de servicio de
los proveedores de datos y de las propias casas de apuestas, y puede acabar
en el cierre de tu cuenta.

---

## Próximos pasos posibles

Si quieres ampliarlo más adelante, algunas ideas:
- Añadir más ligas (Champions, Copa del Rey, etc. — solo cambia el
  diccionario `LIGAS` en `bot.py` con el ID correspondiente de API-Football)
- Guardar tus seguimientos en un archivo en vez de en memoria, para que no
  se pierdan si el bot se reinicia
- Añadir un comando `/cuotas` que compare cuotas de varias casas
