import logging
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ConversationHandler, ContextTypes, MessageHandler, filters
import os
import mimetypes
import hashlib
import sys
import json

# Hash de la clave generada
HASH_CLAVE = "2120ea176dd154dd53820460561c825d3b9a70d8d46b7da5605fb455adfcbb1d"

def verificar_clave():
    clave = input("🔐 Ingresa la clave para ejecutar el bot: ")
    clave_hash = hashlib.sha256(clave.encode()).hexdigest()

    if clave_hash == HASH_CLAVE:
        print("✅ Clave correcta. Ejecutando el bot.")
        return True
    else:
        print("❌ Clave incorrecta. Deteniendo ejecución.")
        return False

# Llamada a la verificación antes de iniciar el bot
if not verificar_clave():
    sys.exit()

print(f"Ruta del script: {os.path.abspath(__file__)}")


print("Iniciando bot...")

# Token del bot y configuraciones de Asana
TOKEN = '7657169297:AAEuxEuYgS7eGUUcjjUCuAxPNlZkd78t4fo'
ASANA_TOKEN = '2/1208796977789197/1208990961126183:f802965e7f1cae629927ba54f6c632c0'
PROJECT_ID = '1208715662807219'
logging.basicConfig(level=logging.INFO)


# Configuraciones globales
ALLOWED_EXTENSIONS = ('.png', '.jpg', '.jpeg')
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
task_id = ''

def cargar_json_seguro(ruta_archivo):
    if os.path.exists(ruta_archivo):
        try:
            with open(ruta_archivo, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            logging.error(f"Error al leer {ruta_archivo}, inicializando como vacío.")
    return {}

notified_tickets_file = "notified_tickets.json"
notified_tickets = cargar_json_seguro(notified_tickets_file)

def guardar_json_seguro(ruta, datos):
    try:
        with open(ruta, "w") as file:
            json.dump(datos, file, indent=4)
    except Exception as e:
        logging.error(f"Error al guardar datos en {ruta}: {e}")

# Al final de `notificar_usuario`
guardar_json_seguro(notified_tickets_file, notified_tickets)

async def reiniciar_conversacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"🔄 Reiniciando la conversación, {user.first_name}. Envia un mensaje para volver a empezar.")

    # Limpiar cualquier dato previo del contexto del usuario
    context.user_data.clear()

    # Finalizar cualquier flujo en curso
    return ConversationHandler.END  # Esto fuerza el cierre del flujo actual

    # Volver al inicio
    await start(update, context)


# IDs del campo personalizado y opciones de Status en Asana
STATUS_FIELD_ID = "1208716880695445"
STATUS_OPTIONS = {
    "Aprobado": "1208716880695448",
    "No Aprobado": "1208716880695449"
}

# Estados de la conversación
TITLE,NAME, PLANT, SECTOR, ISSUE_TYPE, DESCRIPTION, ATTACHMENT, CHECK_TICKET = range(8)

# Función para guardar el ID del ticket asociado a un usuario
def guardar_ticket_activo(user_id, ticket_id):
    tickets_file = "tickets_activos.json"

    # Cargar datos existentes
    if os.path.exists(tickets_file):
        with open(tickets_file, "r") as file:
            tickets_data = json.load(file)
    else:
        tickets_data = {}

    # Agregar el ticket al usuario
    if str(user_id) not in tickets_data:
        tickets_data[str(user_id)] = []
    tickets_data[str(user_id)].append(ticket_id)

    # Guardar los datos actualizados
    with open(tickets_file, "w") as file:
        json.dump(tickets_data, file, indent=4)

def eliminar_ticket_json(user_id, ticket_id):
    ruta_json = "tickets_usuario.json"
    try:
        # Cargar el archivo JSON
        if os.path.exists(ruta_json):
            with open(ruta_json, "r") as archivo:
                datos = json.load(archivo)
        else:
            datos = {}

        # Eliminar el ticket si existe
        if str(user_id) in datos and ticket_id in datos[str(user_id)]:
            datos[str(user_id)].remove(ticket_id)
            # Guardar el archivo JSON actualizado
            with open(ruta_json, "w") as archivo:
                json.dump(datos, archivo, indent=4)
            logging.info(f"Ticket {ticket_id} eliminado del JSON para el usuario {user_id}.")
    except Exception as e:
        logging.error(f"Error al eliminar el ticket del JSON: {e}")

def cargar_json_seguro(ruta_archivo):
    """
    Carga un archivo JSON de forma segura. Si el archivo está vacío o no existe,
    devuelve un diccionario vacío.
    """
    if os.path.exists(ruta_archivo):
        try:
            with open(ruta_archivo, "r") as file:
                data = json.load(file)
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            logging.error(f"Error al leer el archivo JSON: {ruta_archivo}. Inicializando como vacío.")
            return {}
    else:
        logging.warning(f"Archivo no encontrado: {ruta_archivo}. Inicializando como vacío.")
        return {}

# Función para obtener tickets asociados a un usuario
def obtener_tickets_usuario(user_id):
    tickets_file = "tickets.json"

    if os.path.exists(tickets_file):
        with open(tickets_file, "r") as file:
            tickets_data = json.load(file)
        return tickets_data.get(str(user_id), [])
    return []

# Función de inicio
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Nuevo Ticket", callback_data="new_ticket")],
        [InlineKeyboardButton("Consultar Estado", callback_data="consult_status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "👋Hola! Soy el bot de soporte de SISTEMAS'.\n\n"
            "Elegi una opción:",
            reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            "👋Hola! Soy el bot de soporte de SISTEMAS'.\n\n"
            "Elegi una opción:",
            reply_markup=reply_markup
        )

async def verificar_estado_tickets(context: ContextTypes.DEFAULT_TYPE):
    """
    Optimiza la verificación del estado de los tickets en Asana y envía notificaciones.
    """
    tickets_file = "tickets_activos.json"
    notified_tickets_file = "notified_tickets.json"
    tickets_sin_status_file = "tickets_sin_status.json"

    # Cargar datos de los archivos JSON
    tickets_activos = cargar_json_seguro(tickets_file)
    notified_tickets = cargar_json_seguro(notified_tickets_file)
    tickets_sin_status = cargar_json_seguro(tickets_sin_status_file)

    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}

    for user_id, tickets in list(tickets_activos.items()):
        tickets_validos = []
        for ticket_id in tickets:
            ticket_data = obtener_datos_ticket(ticket_id, headers)
            if not ticket_data:
                continue  # Si no hay datos, pasar al siguiente ticket

            # Si el ticket está completado
            if ticket_data.get("completed"):
                if not ticket_ya_notificado(user_id, ticket_id, notified_tickets):
                    await notificar_usuario(context.bot, user_id, ticket_id, ticket_data, notified_tickets)
                    agregar_a_tickets_sin_status(user_id, ticket_id, tickets_sin_status)
                    marcar_ticket_notificado(user_id, ticket_id, notified_tickets)
            else:
                tickets_validos.append(ticket_id)

        # Actualizar lista de tickets activos
        tickets_activos[user_id] = tickets_validos

    # Guardar cambios en los archivos JSON
    guardar_json_seguro(tickets_file, tickets_activos)
    guardar_json_seguro(notified_tickets_file, notified_tickets)
    guardar_json_seguro(tickets_sin_status_file, tickets_sin_status)


def obtener_datos_ticket(ticket_id, headers):
    """
    Realiza una solicitud a la API de Asana para obtener los datos del ticket.
    """
    url = f"https://app.asana.com/api/1.0/tasks/{ticket_id}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("data", {})
    elif response.status_code == 404:
        logging.info(f"Ticket {ticket_id} no encontrado. Eliminándolo.")
    else:
        logging.error(f"Error al obtener el ticket {ticket_id}: {response.status_code}")
    return None


def ticket_ya_notificado(user_id, ticket_id, notified_tickets):
    """
    Verifica si un ticket ya fue notificado al usuario.
    """
    return user_id in notified_tickets and ticket_id in notified_tickets[user_id]


async def notificar_usuario(bot, user_id, ticket_id, ticket_data, notified_tickets):
    """
    Envía una notificación al usuario sobre el ticket completado y actualiza la lista de notificados.
    """
    if ticket_ya_notificado(user_id, ticket_id, notified_tickets):
        return  # Evitar duplicados
    
    try:
        # Enviar notificación al usuario solo si no ha sido notificado antes
        if user_id not in notified_tickets or ticket_id not in notified_tickets[user_id]:
            await bot.send_message(
                chat_id=user_id,
                text=(f"✅ Tu ticket con ID `{ticket_id}` ha sido cerrado.\n\n"
                      f"Nombre: {ticket_data.get('name', 'Sin nombre')}\n"
                      f"Notas: {ticket_data.get('notes', 'Sin descripción')}\n"
                      f"¡Gracias por usar el sistema!\n\n"
                      f"Selecciona una opción para actualizar el estado del ticket:"),
                parse_mode="Markdown"
            )
            
            # Enviar opciones de estado una sola vez
            await enviar_opciones_status(bot, user_id, ticket_id)

            # Marcar como notificado
            if user_id not in notified_tickets:
                notified_tickets[user_id] = []
            notified_tickets[user_id].append(ticket_id)

            # Guardar el estado actualizado en el archivo JSON
            guardar_json_seguro("notified_tickets.json", notified_tickets)

    except Exception as e:
        logging.error(f"Error al enviar notificación o actualizar JSON para el usuario {user_id}: {e}")

def agregar_a_tickets_sin_status(user_id, ticket_id, tickets_sin_status):
    """
    Agrega un ticket a la lista de tickets sin estado.
    """
    if user_id not in tickets_sin_status:
        tickets_sin_status[user_id] = []
    tickets_sin_status[user_id].append(ticket_id)


def marcar_ticket_notificado(user_id, ticket_id, notified_tickets):
    """
    Marca un ticket como notificado para evitar notificaciones duplicadas.
    """
    if user_id not in notified_tickets:
        notified_tickets[user_id] = []
    notified_tickets[user_id].append(ticket_id)


def guardar_json_seguro(ruta, datos):
    """
    Guarda datos en un archivo JSON de forma segura.
    """
    try:
        with open(ruta, "w") as file:
            json.dump(datos, file, indent=4)
    except Exception as e:
        logging.error(f"Error al guardar datos en {ruta}: {e}")

async def enviar_opciones_status(bot, user_id, ticket_id):
    """
    Envía botones para seleccionar entre Aprobado o No Aprobado al cerrar un ticket.
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Aprobado", callback_data=f"status:{ticket_id}:Aprobado"),
            InlineKeyboardButton("❌ No Aprobado", callback_data=f"status:{ticket_id}:No Aprobado"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await bot.send_message(
            chat_id=user_id,
            text="Por favor, selecciona el estado de la tarea:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error al enviar botones de estado al usuario {user_id}: {e}")


async def new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Por favor, pone un título para tu inconveniente:")
    return TITLE

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Detectar si se envió el comando /reiniciar
    if update.message and update.message.text == "/reiniciar":
        return await reiniciar_conversacion(update, context)

    # Guarda el título proporcionado por el usuario
    context.user_data['title'] = update.message.text

    await update.message.reply_text("Por favor, pone tu nombre:")
    return NAME


async def ask_plant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guarda el nombre proporcionado por el usuario
    context.user_data['name'] = update.message.text
    if update.message and update.message.text == "/reiniciar":
        return await reiniciar_conversacion(update, context)

    # Botones de Sucursal
    keyboard = [
        [InlineKeyboardButton("Córdoba", callback_data="Córdoba"),
         InlineKeyboardButton("Spinazzola", callback_data="Spinazzola")],
        [InlineKeyboardButton("Migueletes", callback_data="Migueletes"),
         InlineKeyboardButton("Saladillo", callback_data="Saladillo")],
        [InlineKeyboardButton("Neuquen", callback_data="Neuquen"),
         InlineKeyboardButton("Mendoza", callback_data="Mendoza")],
        [InlineKeyboardButton("Defensa", callback_data="Defensa")]  
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("🏬 Selecciona tu sucursal:", reply_markup=reply_markup)
    return PLANT

async def handle_plant_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.callback_query and update.callback_query.data == "/reiniciar":
        return await reiniciar_conversacion(update, context)

    # Guarda la sucursal seleccionada
    sucursal = query.data
    context.user_data['plant'] = sucursal

    # Lógica según la sucursal seleccionada
    if sucursal == "Defensa":
        # Mostrar todas las áreas originales
        keyboard = [
            [InlineKeyboardButton("Ventas", callback_data="Ventas"),
             InlineKeyboardButton("Contaduría", callback_data="Contaduría")],
            [InlineKeyboardButton("Compras", callback_data="Compras"),
             InlineKeyboardButton("Comex", callback_data="Comex")],
            [InlineKeyboardButton("Mantenimiento", callback_data="Mantenimiento"),
             InlineKeyboardButton("Sistemas", callback_data="Sistemas")],
            [InlineKeyboardButton("Calidad", callback_data="Calidad"),
             InlineKeyboardButton("Laboratorio", callback_data="Laboratorio")],
            [InlineKeyboardButton("Marketing", callback_data="Marketing"),
             InlineKeyboardButton("Tesorería", callback_data="Tesorería")],
            [InlineKeyboardButton("RRHH", callback_data="RRHH"),
             InlineKeyboardButton("Economía", callback_data="Economía")],
            [InlineKeyboardButton("Gerencia", callback_data="Gerencia")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Selecciona el área de Defensa:", reply_markup=reply_markup)
        return SECTOR

    elif sucursal == "Migueletes":
        context.user_data['area'] = "Producción-Rossi"
        await query.message.reply_text("Área asignada automáticamente: Producción Rossi.")
    elif sucursal == "Spinazzola":
        context.user_data['area'] = "Expedición"
        await query.message.reply_text("Área asignada automáticamente: Expedición.")
    elif sucursal == "Mendoza":
        context.user_data['area'] = "Ventas-Mendoza"
        await query.message.reply_text("Área asignada automáticamente: Ventas Mendoza.")
    elif sucursal == "Neuquen":
        context.user_data['area'] = "Ventas-Neuquén"
        await query.message.reply_text("Área asignada automáticamente: Ventas Neuquén.")
    elif sucursal == "Córdoba":
        context.user_data['area'] = "Ventas-Córdoba"
        await query.message.reply_text("Área asignada automáticamente: Ventas Córdoba.")
    elif sucursal == "Saladillo":
        # Botones específicos para Saladillo
        keyboard = [
            [InlineKeyboardButton("Contaduría-Saladillo", callback_data="Contaduría-Saladillo"),
             InlineKeyboardButton("Ventas-Saladillo", callback_data="Ventas-Saladillo")],
            [InlineKeyboardButton("Producción-Saladillo", callback_data="Producción-Saladillo")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Selecciona el área de Saladillo:", reply_markup=reply_markup)
        return SECTOR
    else:
        await query.message.reply_text("Sucursal no reconocida. Reinicia el proceso.\n Envia cualquier mensaje para volver a empezar.")
        return ConversationHandler.END

    # Si el área se asignó automáticamente, saltar al siguiente paso
    return await ask_issue_type(update, context)


async def ask_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text == "/reiniciar":
        return await reiniciar_conversacion(update, context)
    query = update.callback_query
    await query.answer()
    context.user_data['plant'] = query.data  # Guarda la sucursal seleccionada
    await query.message.reply_text("¿En qué sector trabajas?")
    return SECTOR


async def ask_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verificar si el usuario ingresó texto válido
    texto = update.message.text
    if not texto.strip():  # Verifica si el texto está vacío
        await update.message.reply_text("❌ Por favor, proporciona una descripción válida.")
        return DESCRIPTION

    # Guardar el sector proporcionado por el usuario
    context.user_data['sector'] = texto
    await update.message.reply_text("Por favor, detalla el problema:")
    return DESCRIPTION

async def handle_invalid_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Entrada no válida. Por favor, selecciona una opción del menú.")
    return ConversationHandler.END


async def create_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['description'] = update.message.text

    url = "https://app.asana.com/api/1.0/tasks"
    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}
    data = {
        "data": {
            "name": context.user_data['title'],
            "notes": (
                f"Sucursal: {context.user_data['plant']}\n"
                f"Área: {context.user_data['area']}\n"
                f"Tipo de inconveniente: {context.user_data['issue_type']}\n"
                f"Descripción: {context.user_data['description']}"
            ),
            "projects": [PROJECT_ID],
            "custom_fields": {
                "1208935940127966": obtener_enum_gid(context.user_data['plant']),
                "1208935888744230": obtener_area_gid(context.user_data['area']),
                "1208715662807242": obtener_issue_gid(context.user_data['issue_type'])
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        global task_id
        task_id = response.json()['data']['gid']

        # Guardar el ticket en el JSON
        guardar_ticket_activo(user_id, task_id)

        # Guardar el ticket_id en context.user_data
        context.user_data['ticket_id'] = task_id

        keyboard = [
        [InlineKeyboardButton("Adjuntar archivo", callback_data="attachment")],
        [InlineKeyboardButton("Finalizar", callback_data="finish")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)


        await update.message.reply_text(
            f"✅ Ticket creado con éxito. ID: {task_id}\n¿Qué deseas hacer ahora?",
            reply_markup=reply_markup
        )
        return ATTACHMENT
    else:
        logging.error(f"Error al crear ticket: {response.status_code} - {response.text}")
        await update.message.reply_text("❌ Error al crear el ticket. Intenta nuevamente.")

    return ConversationHandler.END

def obtener_detalles_ticket(ticket_id, user_id=None):
    url = f"https://app.asana.com/api/1.0/tasks/{ticket_id}"
    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}

    response = reintentar_operacion(requests.get, 3, 3, url, headers=headers)
    if response and response.status_code == 200:
        data = response.json()['data']
        nombre = data.get('name', 'Sin nombre')
        notas = data.get('notes', 'Sin descripción')
        estado = "Completado" if data.get('completed') else "Abierto"
        return f"📝 *Nombre:* {nombre}\n📄 *Descripción:* {notas}\n✅ *Estado:* {estado}"
    elif response and response.status_code == 404:
        logging.error(f"❌ Ticket {ticket_id} no encontrado en Asana. Eliminándolo del registro.")
        if user_id:
            eliminar_ticket_json(user_id, ticket_id)
        return None
    elif response:
        logging.error(f"Error al obtener detalles del ticket {ticket_id}: {response.status_code}")
        return None
    else:
        logging.error(f"❌ No se recibió respuesta de Asana para el ticket {ticket_id}.")
        return None

def actualizar_tickets_usuario(user_id, tickets_validos):
    ruta_json = "tickets_usuario.json"
    try:
        # Cargar el archivo JSON
        if os.path.exists(ruta_json):
            with open(ruta_json, "r") as archivo:
                datos = json.load(archivo)
        else:
            datos = {}

        # Actualizar la lista de tickets
        datos[str(user_id)] = tickets_validos

        # Guardar el archivo JSON actualizado
        with open(ruta_json, "w") as archivo:
            json.dump(datos, archivo, indent=4)
        logging.info(f"Lista de tickets actualizada para el usuario {user_id}.")
    except Exception as e:
        logging.error(f"Error al actualizar los tickets en el JSON: {e}")

def obtener_botones_sector(sucursal):
    # Opciones de botones según la sucursal seleccionada
    opciones = {
        "Defensa": [
            [InlineKeyboardButton("Gerencia", callback_data="Gerencia"),
             InlineKeyboardButton("Contaduría", callback_data="Contaduría")],
            [InlineKeyboardButton("Ventas", callback_data="Ventas"),
             InlineKeyboardButton("Comex", callback_data="Comex")],
            [InlineKeyboardButton("Mantenimiento", callback_data="Mantenimiento"),
             InlineKeyboardButton("Sistemas", callback_data="Sistemas")],
            [InlineKeyboardButton("Calidad", callback_data="Calidad"),
             InlineKeyboardButton("Laboratorio", callback_data="Laboratorio")],
            [InlineKeyboardButton("Marketing", callback_data="Marketing"),
             InlineKeyboardButton("Tesorería", callback_data="Tesorería")],
            [InlineKeyboardButton("RRHH", callback_data="RRHH"),
             InlineKeyboardButton("Economía", callback_data="Economía")],
            [InlineKeyboardButton("Compras", callback_data="Compras")]
        ],
        "Rossi": [
            [InlineKeyboardButton("Producción Rossi", callback_data="Producción-Rossi")]
        ],
        "Neuquen": [
            [InlineKeyboardButton("Ventas Neuquén", callback_data="Ventas-Neuquén")]
        ],
        "Mendoza": [
            [InlineKeyboardButton("Ventas Mendoza", callback_data="Ventas-Mendoza")]
        ]
    }

    # Retorna los botones correspondientes a la sucursal seleccionada
    return opciones.get(sucursal, [])


def obtener_enum_gid(sucursal):
    opciones = {
        "Defensa": "1208935940127967",
        "Spinazzola": "1208935940127968",
        "Migueletes": "1208935940127969",
        "Saladillo": "1208935940127970",
        "Neuquen": "1208935880801247",
        "Mendoza": "1208935880801248"
    }
    return opciones.get(sucursal, None)
def obtener_area_gid(area):
    opciones = {
        "Gerencia": "1208935888744231",
        "Ventas": "1208935888744232",
        "Contaduría": "1208936008031771",
        "Expedición": "1208936008031772",
        "Comex": "1208936008031773",
        "Sistemas": "1208936008031774",
        "Mantenimiento": "1208936008031775",
        "Calidad": "1208936008031776",
        "Laboratorio": "1208936008031777",
        "Marketing": "1208936008031778",
        "Tesorería": "1208935939438169",
        "RRHH": "1208935878300065",
        "Ventas-Saladillo": "1208936163838572",
        "Ventas-Neuquén": "1208936163838573",
        "Ventas-Mendoza": "1208936163838574",
        "Contaduría-Saladillo": "1208936163838575",
        "Producción-Rossi": "1208945344581801",
        "Producción-Saladillo": "1208945344581802",
        "Economía": "1208960048709807",
        "Compras": "1208960674472810",
        "Ventas-Córdoba": "1209009390260768"
    }
    return opciones.get(area, None)

import time
from telegram.error import TimedOut

# Función que reintenta la operación en caso de timeout
def reintentar_operacion(funcion, max_reintentos=3, espera=3, *args, **kwargs):
    for intento in range(max_reintentos):
        try:
            return funcion(*args, **kwargs)
        except TimedOut:
            logging.warning(f"Timeout detectado. Reintentando... ({intento+1}/{max_reintentos})")
            time.sleep(espera)
        except Exception as e:
            logging.error(f"Error inesperado: {e}")
            break
    logging.error("❌ No se pudo completar la operación después de múltiples intentos.")
    return None

def eliminar_ticket_de_json(ticket_id, archivos):
    try:
        for archivo in archivos:
            if os.path.exists(archivo):
                with open(archivo, "r") as file:
                    data = json.load(file)

                for user_id, tickets in data.items():
                    if ticket_id in tickets:
                        tickets.remove(ticket_id)
                        break

                with open(archivo, "w") as file:
                    json.dump(data, file, indent=4)

        logging.info(f"Ticket {ticket_id} eliminado de los archivos: {archivos}")
    except Exception as e:
        logging.error(f"Error al eliminar el ticket {ticket_id} de los archivos JSON: {e}")



async def ask_sector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Botones del área de la empresa
    keyboard = [
        [InlineKeyboardButton("Gerencia", callback_data="Gerencia"),
         InlineKeyboardButton("Ventas", callback_data="Ventas")],
        [InlineKeyboardButton("Contaduría", callback_data="Contaduría"),
         InlineKeyboardButton("Expedición", callback_data="Expedición")],
        [InlineKeyboardButton("Comex", callback_data="Comex"),
         InlineKeyboardButton("Sistemas", callback_data="Sistemas")],
        [InlineKeyboardButton("Mantenimiento", callback_data="Mantenimiento"),
         InlineKeyboardButton("Calidad", callback_data="Calidad")],
        [InlineKeyboardButton("Laboratorio", callback_data="Laboratorio"),
         InlineKeyboardButton("Marketing", callback_data="Marketing")],
        [InlineKeyboardButton("Tesorería", callback_data="Tesorería"),
         InlineKeyboardButton("RRHH", callback_data="RRHH")],
        [InlineKeyboardButton("Ventas-Saladillo", callback_data="Ventas-Saladillo"),
         InlineKeyboardButton("Ventas-Neuquén", callback_data="Ventas-Neuquén")],
        [InlineKeyboardButton("Ventas-Mendoza", callback_data="Ventas-Mendoza"),
         InlineKeyboardButton("Contaduría-Saladillo", callback_data="Contaduría-Saladillo")],
        [InlineKeyboardButton("Producción-Rossi", callback_data="Producción-Rossi"),
         InlineKeyboardButton("Producción-Saladillo", callback_data="Producción-Saladillo")],
        [InlineKeyboardButton("Economía", callback_data="Economía"),
         InlineKeyboardButton("Compras", callback_data="Compras")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Selecciona el área de la empresa:", reply_markup=reply_markup)

    return SECTOR

async def list_user_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Cargar los archivos JSON
    tickets_file = "tickets_activos.json"
    tickets_sin_status_file = "tickets_sin_status.json"

    tickets_activos = {}
    tickets_sin_status = {}

    # Cargar tickets activos
    if os.path.exists(tickets_file):
        with open(tickets_file, "r") as file:
            tickets_activos = json.load(file)

    # Cargar tickets sin estado
    if os.path.exists(tickets_sin_status_file):
        with open(tickets_sin_status_file, "r") as file:
            tickets_sin_status = json.load(file)

    # Inicializar variables
    mensaje = "📋 *Tus tickets creados:*\n\n"
    tickets_validos = []  # Para almacenar tickets válidos
    has_tickets = False  # Para comprobar si hay tickets

    # Headers para la solicitud a Asana
    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}

    # Verificar tickets activos
    if user_id in tickets_activos:
        for ticket_id in tickets_activos[user_id]:
            url = f"https://app.asana.com/api/1.0/tasks/{ticket_id}"
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                ticket_data = response.json().get("data", {})
                mensaje += (
                    f"✅ *ID del ticket:* `{ticket_id}`\n"
                    f"🔖 *Nombre:* {ticket_data.get('name', 'Sin nombre')}\n"
                    f"📄 *Notas:* {ticket_data.get('notes', 'Sin descripción')}\n"
                    f"🏷️ *Estado:* {'Completado' if ticket_data.get('completed') else 'Abierto'}\n\n"
                )
                tickets_validos.append(ticket_id)
                has_tickets = True

    # Verificar tickets sin estado
    if user_id in tickets_sin_status:
        for ticket_id in tickets_sin_status[user_id]:
            url = f"https://app.asana.com/api/1.0/tasks/{ticket_id}"
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                ticket_data = response.json().get("data", {})
                mensaje += (
                    f"🟡 *ID del ticket:* `{ticket_id}`\n"
                    f"🔖 *Nombre:* {ticket_data.get('name', 'Sin nombre')}\n"
                    f"📄 *Notas:* {ticket_data.get('notes', 'Sin descripción')}\n"
                    f"🏷️ *Estado:* Sin definir\n\n"
                )
                tickets_validos.append(ticket_id)
                has_tickets = True

    # Si no hay tickets
    if not has_tickets:
        mensaje = "❌ No tienes tickets creados."

    # Enviar mensaje al usuario
    await update.callback_query.message.reply_text(mensaje, parse_mode="Markdown")

    # Actualizar archivo JSON con tickets válidos
    if user_id in tickets_activos:
        tickets_activos[user_id] = tickets_validos
        with open(tickets_file, "w") as file:
            json.dump(tickets_activos, file, indent=4)

    return ConversationHandler.END


async def handle_area_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Detectar si se envió el comando /reiniciar
    if update.callback_query and update.callback_query.data == "/reiniciar":
        return await reiniciar_conversacion(update, context)

    query = update.callback_query
    await query.answer()

    # Guarda el área seleccionada
    context.user_data['area'] = query.data

    # Confirma la selección
    await query.message.reply_text(f"Seleccionaste el área: {query.data}")

    # Ahora pide el tipo de inconveniente
    return await ask_issue_type(update, context)


async def ask_for_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Por favor, envía una imagen en formato PNG, JPG o JPEG (máximo 5 MB).")
    return ATTACHMENT

    
# Límite máximo de imágenes permitidas
MAX_IMAGES = 3

async def handle_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'ticket_id' not in context.user_data or not context.user_data['ticket_id']:
        await update.message.reply_text("❌ No se encontró un ticket asociado. Por favor, crea un ticket antes de adjuntar un archivo.")
        return ConversationHandler.END

    # Inicializar el contador de imágenes si no existe
    if 'attachment_count' not in context.user_data:
        context.user_data['attachment_count'] = 0

    # Verificar si ya se alcanzó el límite de imágenes
    if context.user_data['attachment_count'] >= MAX_IMAGES:
        await update.message.reply_text("Has alcanzado el límite máximo de imágenes permitidas para este ticket.")
        return ConversationHandler.END

    file = None
    file_name = ""

    # Detectar si el archivo es un documento o una foto
    if update.message.document:
        file = update.message.document
        file_name = file.file_name
    elif update.message.photo:
        file = update.message.photo[-1]
        file_name = f"photo_{context.user_data['attachment_count'] + 1}.jpg"
    else:
        await update.message.reply_text("Formato no permitido. Solo se aceptan archivos PNG, JPG o JPEG.")
        return ATTACHMENT

    # Validar y procesar el archivo
    if file and file_name.lower().endswith(ALLOWED_EXTENSIONS):
        if file.file_size > MAX_FILE_SIZE:
            await update.message.reply_text("El archivo es demasiado grande. Máximo permitido: 5 MB.")
            return ATTACHMENT

        try:
            file_id = file.file_id
            new_file = await context.bot.get_file(file_id)
            file_path = f"{file_name}"
            await new_file.download_to_drive(file_path)

            if os.path.exists(file_path):
                mime_type, _ = mimetypes.guess_type(file_path)
                with open(file_path, "rb") as f:
                    files = {"file": (file_name, f, mime_type)}
                    data = {"parent": context.user_data['ticket_id']}
                    url = "https://app.asana.com/api/1.0/attachments"
                    response = requests.post(url, headers={"Authorization": f"Bearer {ASANA_TOKEN}"}, data=data, files=files)

                    if response.status_code == 200:
                        # Incrementar el contador de imágenes adjuntadas
                        context.user_data['attachment_count'] += 1
                        count = context.user_data['attachment_count']
                        await update.message.reply_text(
                            f"El archivo se ha adjuntado correctamente al ticket. ({count}/{MAX_IMAGES})"
                        )

                        # Mostrar botones para adjuntar más imágenes o finalizar
                        keyboard = [
                            [InlineKeyboardButton("Finalizar", callback_data="finish")]
                        ]
                        if count < MAX_IMAGES:
                            keyboard.insert(0, [InlineKeyboardButton("Sí", callback_data="attach_more")])
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await update.message.reply_text("¿Deseas adjuntar otra imagen?", reply_markup=reply_markup)
                    else:
                        await update.message.reply_text(f"Error al adjuntar el archivo: {response.status_code}")
            else:
                await update.message.reply_text("Error al descargar el archivo. Inténtalo nuevamente.")
        except Exception as e:
            logging.error(f"Error al manejar el archivo: {e}")
            await update.message.reply_text("Ocurrió un error al procesar el archivo. Inténtalo nuevamente.")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await update.message.reply_text("Formato no permitido. Solo se aceptan archivos PNG, JPG o JPEG.")

    return ATTACHMENT


async def handle_attachment_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "attach_more":
        await query.message.reply_text("Por favor, envía otra imagen en formato PNG, JPG o JPEG (máximo 5 MB).")
        return ATTACHMENT
    elif query.data == "finish":
        await query.message.reply_text("Adjunto finalizado. Envia un mensaje para reinciar el proceso.")
        # Reiniciar el flujo
        return ConversationHandler.END

async def handle_attachment_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "attach_more":
        await query.message.reply_text("Por favor, envía otra imagen en formato PNG, JPG o JPEG (máximo 5 MB).")
        return ATTACHMENT
    elif query.data == "finish":
        await query.message.reply_text("Adjunto finalizado. Envia un mensaje para reinciar el proceso.")
        return ConversationHandler.END

async def handle_attach_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "attach_more":
        await query.message.reply_text("Por favor, envía otra imagen en formato PNG, JPG o JPEG (máximo 5 MB).")
        return ATTACHMENT
    elif query.data == "finish":
        await query.message.reply_text("¡Gracias! El ticket ha sido completado.")
        return ConversationHandler.END

ATTACHMENT_STATE = [
    CallbackQueryHandler(handle_attach_more, pattern="^(attach_more|finish)$"),
    MessageHandler(filters.ALL, handle_attachment),
]

async def ask_ticket_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Por favor, ingresa el ID del ticket que deseas consultar:")
    return CHECK_TICKET

async def check_ticket_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = update.message.text
    url = f"https://app.asana.com/api/1.0/tasks/{ticket_id}"
    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        ticket_data = response.json()['data']
        name = ticket_data.get('name', 'Sin nombre')
        notes = ticket_data.get('notes', 'Sin descripción')
        completed = ticket_data.get('completed', False)

        status = "Completado" if completed else "Abierto"
        await update.message.reply_text(
            f"Estado del Ticket\n\n"
            f"ID: {ticket_id}\n"
            f"Nombre: {name}\n"
            f"Descripción: {notes}\n"
            f"Estado: {status}"
        )
    else:
        await update.message.reply_text(f"No se encontró un ticket con el ID: {ticket_id}. Verifica el ID.")
    return ConversationHandler.END

# Volver al menú principal después de cualquier mensaje
async def reset_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
  
async def ask_issue_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Detectar si se envió el comando /reiniciar
    if update.callback_query and update.callback_query.data == "/reiniciar":
        return await reiniciar_conversacion(update, context)

    keyboard = [
        [InlineKeyboardButton("🛠️ Soporte General / Soporte IT", callback_data="Soporte IT"),
         InlineKeyboardButton("📉 Visionaris / Intelektron", callback_data="Visionaris")],
        [InlineKeyboardButton("🧑‍💻 Desarrollo / Softland", callback_data="Desarrollo"),
         InlineKeyboardButton("🌐 Web", callback_data="Web")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.reply_text("🔧 Defina el tipo de inconveniente:", reply_markup=reply_markup)
    return ISSUE_TYPE


async def handle_issue_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Lista de opciones válidas
    opciones_validas = ["Soporte IT", "Visionaris", "Desarrollo", "Web"]

    # Verificar si la opción es válida
    if query.data not in opciones_validas:
        await query.message.reply_text("❌ Opción no válida. Por favor, selecciona una opción válida del menú.")
        return ISSUE_TYPE

    # Guarda el tipo de inconveniente seleccionado
    context.user_data['issue_type'] = query.data

    # Confirma la selección y pide la descripción
    await query.message.reply_text(f"Seleccionaste el tipo de inconveniente: {query.data}")
    await query.message.reply_text("Por favor, a continuacion detalla el problema:")
    return DESCRIPTION

# Finaliza la conversación
async def end_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global task_id
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        f"✅ ¡Proceso finalizado! ID: {task_id}\nSi deseas generar un nuevo ticket o consultar el estado, usa el menú."
    )
    await start(update, context)  # Vuelve al menú principal
    return ConversationHandler.END  # Finaliza la conversación

def mover_ticket_entre_json(ticket_id, origen_file, destino_file):
    try:
        # Cargar archivos JSON
        if os.path.exists(origen_file):
            with open(origen_file, "r") as file:
                origen_data = json.load(file)
        else:
            origen_data = {}

        if os.path.exists(destino_file):
            with open(destino_file, "r") as file:
                destino_data = json.load(file)
        else:
            destino_data = {}

        # Mover el ticket
        for user_id, tickets in origen_data.items():
            if ticket_id in tickets:
                tickets.remove(ticket_id)
                if user_id not in destino_data:
                    destino_data[user_id] = []
                destino_data[user_id].append(ticket_id)
                break

        # Guardar los cambios
        with open(origen_file, "w") as file:
            json.dump(origen_data, file, indent=4)

        with open(destino_file, "w") as file:
            json.dump(destino_data, file, indent=4)

        logging.info(f"Ticket {ticket_id} movido de {origen_file} a {destino_file}.")
    except Exception as e:
        logging.error(f"Error al mover el ticket {ticket_id} entre archivos JSON: {e}")


def obtener_issue_gid(issue_type):
    opciones = {
        "Soporte IT": "1208715667639797",
        "Visionaris": "1208715667639798",
        "Desarrollo": "1208715667639799",
        "Web": "1208824934434917"
    }
    return opciones.get(issue_type, None)

async def enviar_opciones_status(bot, user_id, ticket_id):
    """
    Envía botones para seleccionar entre Aprobado o No Aprobado al cerrar un ticket.
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Aprobado", callback_data=f"status:{ticket_id}:Aprobado"),
            InlineKeyboardButton("❌ No Aprobado", callback_data=f"status:{ticket_id}:No Aprobado"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await bot.send_message(
            chat_id=user_id,
            text="Por favor, selecciona el estado de la tarea:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error al enviar botones de estado al usuario {user_id}: {e}")


async def handle_status_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Extraer ticket_id y la selección de status del callback_data
    data = query.data.split(":")
    if len(data) != 3 or data[0] != "status":
        await query.message.reply_text("Datos inválidos. Por favor, intenta de nuevo.")
        return

    ticket_id, status_name = data[1], data[2]
    status_gid = STATUS_OPTIONS.get(status_name)

    if not status_gid:
        await query.message.reply_text("Estado inválido. Por favor, intenta de nuevo.")
        return

    # Actualizar el campo personalizado Status en Asana
    url = f"https://app.asana.com/api/1.0/tasks/{ticket_id}"
    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}
    data = {
        "data": {
            "custom_fields": {
                STATUS_FIELD_ID: status_gid
            }
        }
    }

    response = requests.put(url, headers=headers, json=data)

    if response.status_code == 200:
        await query.message.reply_text(f"✅ El estado del ticket {ticket_id} se ha actualizado a '{status_name}'.")

        # Si el ticket fue aprobado, eliminarlo de ambos archivos JSON
        if status_name == "Aprobado":
            eliminar_ticket_de_json(ticket_id, ["tickets_activos.json", "tickets_sin_status.json"])

        # Si el ticket fue no aprobado, moverlo de `tickets_sin_status.json` a `tickets_activos.json`
        elif status_name == "No Aprobado":
            mover_ticket_entre_json(ticket_id, "tickets_sin_status.json", "tickets_activos.json")
            await query.message.reply_text(f"🔄 Tu ticket {ticket_id} ha sido devuelto a los tickets activos para continuar con el seguimiento.")
    else:
        await query.message.reply_text(f"❌ Error al actualizar el estado del ticket: {response.status_code}")
        logging.error(f"Error al actualizar el estado: {response.text}")

    # Volver al menú principal
    await start(update, context)



    # Modificar la lógica de envío del mensaje de finalización de ticket
async def enviar_mensaje_finalizacion(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id, ticket_data):
    """
    Envía un mensaje de finalización con los detalles del ticket y despliega los botones de Status.
    """
    mensaje = (
        f"✅ Tu ticket con ID {ticket_id} ha sido cerrado.\n\n"
        f"Nombre: {ticket_data.get('name', 'N/A')}\n"
        f"Notas: {ticket_data.get('notes', 'N/A')}\n"
        f"Área: {ticket_data.get('custom_fields', {}).get('area', 'N/A')}\n"
        f"Tipo de inconveniente: {ticket_data.get('custom_fields', {}).get('issue_type', 'N/A')}\n"
        f"Descripción: {ticket_data.get('notes', 'N/A')}\n"
        f"¡Gracias por usar el sistema!\n"
    )

    await update.message.reply_text(mensaje)
    await enviar_opciones_status(update, context, ticket_id)
 

application = Application.builder().token(TOKEN).arbitrary_callback_data(True).build()

application.job_queue.run_repeating(
    verificar_estado_tickets,
    interval=60,  # Intervalo en segundos (1 minuto)
    first=10      # Comienza después de 10 segundos
)


ATTACHMENT_HANDLER = [
    CallbackQueryHandler(handle_attachment_buttons, pattern="^(attach_more|finish)$"),  # Maneja botones de Sí/No
    MessageHandler(filters.ALL, handle_attachment)  # Maneja archivos enviados por el usuario
]

new_ticket_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(new_ticket, pattern="^new_ticket$")],
    states={
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_plant)],
        PLANT: [CallbackQueryHandler(handle_plant_selection)],
        SECTOR: [CallbackQueryHandler(handle_area_selection)],
        ISSUE_TYPE: [CallbackQueryHandler(handle_issue_type_selection)],
        DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_ticket)],
        ATTACHMENT: [
    CallbackQueryHandler(ask_for_attachment, pattern="^attachment$"),  # Botón "Adjuntar archivo"
    CallbackQueryHandler(handle_attachment_buttons, pattern="^(attach_more|finish)$"),  # Botones "Sí" y "No"
    MessageHandler(filters.ALL, handle_attachment),  # Procesar archivo enviado
],

    },
    fallbacks=[
        CommandHandler("reiniciar", reiniciar_conversacion),
        MessageHandler(filters.ALL, handle_invalid_input)  # Fallback global
    ]
)


consult_status_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(list_user_tickets, pattern="^consult_status$")],
    states={
        CHECK_TICKET: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_ticket_status)],
    },
    fallbacks=[CommandHandler("reiniciar", reiniciar_conversacion)]  # Fallback global
)

# Agregar el job al inicio del bot
application.job_queue.run_repeating(
    verificar_estado_tickets,
    interval=60,  # Intervalo en segundos (1 minuto)
    first=10      # Comienza después de 10 segundos
)

# Agregar manejadores y configurar el bot
application.add_handler(CommandHandler("start", start))  # Comando /start
application.add_handler(new_ticket_handler)  # Manejo de nuevos tickets
application.add_handler(consult_status_handler)  # Consulta de estado
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reset_to_start))  # Reiniciar flujo con cualquier mensaje
application.add_handler(CommandHandler("reiniciar", reiniciar_conversacion))  # Comando /reiniciar

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_user:
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="❌ Ocurrió un error inesperado. Por favor, intenta nuevamente más tarde."
            )
        except Exception as e:
            logging.error(f"Error al notificar al usuario sobre el error: {e}")

if __name__ == "__main__":
    # Configurá el JobQueue para ejecutar una única instancia
    if application.job_queue and not application.job_queue.jobs():
        application.job_queue.run_repeating(
            verificar_estado_tickets,
            interval=60,  # Intervalo de 60 segs
            first=10      # Comienza después de 10 segundos
        )

    # Agregar manejadores (incluyendo /reiniciar)
    application.add_handler(CommandHandler("reiniciar",  reiniciar_conversacion))

    # Ejecutar el bot
    application.run_polling()