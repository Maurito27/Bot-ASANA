import logging
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ConversationHandler, ContextTypes, MessageHandler, filters
import os
import mimetypes
import hashlib
import sys

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

print("Iniciando bot...")

# Token del bot y configuraciones de Asana
TOKEN = '7657169297:AAEuxEuYgS7eGUUcjjUCuAxPNlZkd78t4fo'
ASANA_TOKEN = '2/1208796977789197/1208990961126183:f802965e7f1cae629927ba54f6c632c0'
PROJECT_ID = '1208715662807219'
logging.basicConfig(level=logging.INFO)

# Configuraciones globales
ALLOWED_EXTENSIONS = ('.png', '.jpg', '.jpeg')
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Estados de la conversación
NAME, PLANT, SECTOR, ISSUE_TYPE, DESCRIPTION, ATTACHMENT, CHECK_TICKET = range(7)

# Función de inicio
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Nuevo Ticket", callback_data="new_ticket")],
        [InlineKeyboardButton("Consultar Estado", callback_data="consult_status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "¡Hola! Soy el bot de soporte de 'Solicitudes SISTEMAS'.\n\n"
            "Elige una opción:",
            reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            "¡Hola! Soy el bot de soporte de 'Solicitudes SISTEMAS'.\n\n"
            "Elige una opción:",
            reply_markup=reply_markup
        )

# Flujo de creación de un nuevo ticket
async def new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Por favor, indicar  nombre y titulo del inconveniente: \n ( Ejemplo\"Mauro-inconveniente de conexion a Internet \")")
    return NAME

async def ask_plant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    
    # Botones de Sucursal
    keyboard = [
        [InlineKeyboardButton("Defensa", callback_data="Defensa"),
         InlineKeyboardButton("Spinazzola", callback_data="Spinazzola")],
        [InlineKeyboardButton("Migueletes", callback_data="Migueletes"),
         InlineKeyboardButton("Saladillo", callback_data="Saladillo")],
        [InlineKeyboardButton("Neuquen", callback_data="Neuquen"),
         InlineKeyboardButton("Mendoza", callback_data="Mendoza")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Selecciona tu sucursal:", reply_markup=reply_markup)
    return PLANT
async def handle_plant_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Guarda la sucursal seleccionada
    context.user_data['plant'] = query.data

    # Confirma la selección
    await query.message.reply_text(f"Seleccionaste la sucursal: {query.data}")

    # Muestra directamente los botones del área (sin reiniciar la conversación)
    return await ask_sector(update, context)

async def ask_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['plant'] = query.data  # Guarda la sucursal seleccionada
    await query.message.reply_text("¿En qué sector trabajas?")
    return SECTOR

async def ask_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['sector'] = update.message.text
    await update.message.reply_text("Por favor describe el problema:")
    return DESCRIPTION

async def create_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'issue_type' not in context.user_data:
        await update.message.reply_text("❌ No se seleccionó el tipo de inconveniente. Por favor reinicia el proceso.")
        return ConversationHandler.END

    context.user_data['description'] = update.message.text

    url = "https://app.asana.com/api/1.0/tasks"
    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}
    data = {
        "data": {
            "name": f"Solicitud de {context.user_data['name']}",
            "notes": (
                f"Sucursal: {context.user_data['plant']}\n"
                f"Área: {context.user_data['area']}\n"
                f"Tipo de inconveniente: {context.user_data['issue_type']}\n"
                f"Descripción: {context.user_data['description']}"
            ),
            "projects": [PROJECT_ID],
            "custom_fields": {
                "1208935940127966": obtener_enum_gid(context.user_data['plant']),  # Sucursal
                "1208935888744230": obtener_area_gid(context.user_data['area']),   # Área
                "1208715662807242": obtener_issue_gid(context.user_data['issue_type'])  # Solicitud de trabajo
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        task_id = response.json()['data']['gid']
        context.user_data['ticket_id'] = task_id  # Guardamos el ID del ticket creado

        keyboard = [
            [InlineKeyboardButton("Adjuntar archivo", callback_data="attachment")],
            [InlineKeyboardButton("Finalizar", callback_data="finish")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ El ticket se creó con éxito. ID: {task_id}\n"
            "¿Deseas adjuntar un archivo o finalizar el proceso?",
            reply_markup=reply_markup
        )
        return ATTACHMENT
    else:
        logging.error(f"Error al crear ticket: {response.status_code} - {response.text}")
        await update.message.reply_text(
            f"❌ Hubo un error al crear el ticket.\nDetalles: {response.status_code} - {response.text}"
        )
        return ConversationHandler.END

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
        "Compras": "1208960674472810"
    }
    return opciones.get(area, None)
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

async def handle_area_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def handle_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = None
    file_path = None
    file_name = ""

    if update.message.document:
        file = update.message.document
        file_name = file.file_name
    elif update.message.photo:
        file = update.message.photo[-1]
        file_name = "photo.jpg"
    else:
        await update.message.reply_text("Formato no permitido. Solo se aceptan archivos PNG, JPG o JPEG.")
        return ATTACHMENT

    if file and file_name.lower().endswith(ALLOWED_EXTENSIONS):
        if file.file_size > MAX_FILE_SIZE:
            await update.message.reply_text("El archivo es demasiado grande. Máximo permitido: 5 MB.")
            return ATTACHMENT
        try:
            logging.info(f"Archivo recibido: Tamaño: {file.file_size}")
            file_id = file.file_id
            new_file = await context.bot.get_file(file_id)
            file_path = f"{file_name}"  # Usar nombre original
            await new_file.download_to_drive(file_path)

            if os.path.exists(file_path):
                mime_type, _ = mimetypes.guess_type(file_path)
                logging.info(f"Archivo descargado exitosamente en: {file_path}, Tipo MIME: {mime_type}")

                with open(file_path, "rb") as f:
                    files = {"file": (file_name, f, mime_type)}
                    data = {"parent": context.user_data['ticket_id']}
                    url = "https://app.asana.com/api/1.0/attachments"
                    response = requests.post(url, headers={"Authorization": f"Bearer {ASANA_TOKEN}"}, data=data, files=files)

                    if response.status_code == 200:
                        await update.message.reply_text("El archivo se ha adjuntado correctamente al ticket. \n Para generar un nuevo ticket, simplemente envia cualquier mensaje para que el bot vuelva a iniciar👺")
                    else:
                        await update.message.reply_text(f"Error al adjuntar el archivo: {response.status_code}")
            else:
                await update.message.reply_text("Error al descargar el archivo. Inténtalo nuevamente.")
        except Exception as e:
            logging.error(f"Error al manejar el archivo: {e}")
            await update.message.reply_text("Ocurrió un error al procesar el archivo. Inténtalo nuevamente.")
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
    else:
        await update.message.reply_text("Formato no permitido. Solo se aceptan archivos PNG, JPG o JPEG.")
    return ConversationHandler.END

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
    keyboard = [
        [InlineKeyboardButton("Soporte General / Soporte IT", callback_data="Soporte IT"),
         InlineKeyboardButton("Visionaris / Intelektron", callback_data="Visionaris")],
        [InlineKeyboardButton("Desarrollo / Softland", callback_data="Desarrollo"),
         InlineKeyboardButton("Web", callback_data="Web")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.reply_text("🔧 Defina el tipo de inconveniente:", reply_markup=reply_markup)
    return ISSUE_TYPE

async def handle_issue_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Guarda el tipo de inconveniente seleccionado
    context.user_data['issue_type'] = query.data

    # Confirma la selección y pide la descripción
    await query.message.reply_text(f"Seleccionaste el tipo de inconveniente: {query.data}")
    await query.message.reply_text("Por favor describe el problema:")
    return DESCRIPTION

def obtener_issue_gid(issue_type):
    opciones = {
        "Soporte IT": "1208715667639797",
        "Visionaris": "1208715667639798",
        "Desarrollo": "1208715667639799",
        "Web": "1208824934434917"
    }
    return opciones.get(issue_type, None)

application = Application.builder().token(TOKEN).build()

new_ticket_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(new_ticket, pattern="^new_ticket$")],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_plant)],
        PLANT: [CallbackQueryHandler(handle_plant_selection)],
        SECTOR: [CallbackQueryHandler(handle_area_selection)],
        ISSUE_TYPE: [CallbackQueryHandler(handle_issue_type_selection)],
        DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_ticket)],
        ATTACHMENT: [
            CallbackQueryHandler(ask_for_attachment, pattern="^attachment$"),
            CallbackQueryHandler(reset_to_start, pattern="^finish$"),
            MessageHandler(filters.ALL, handle_attachment)
        ]
    },
    fallbacks=[]
)

consult_status_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(ask_ticket_id, pattern="^consult_status$")],
    states={
        CHECK_TICKET: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_ticket_status)],
    },
    fallbacks=[]
)

application.add_handler(CommandHandler("start", start))
application.add_handler(new_ticket_handler)
application.add_handler(consult_status_handler)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reset_to_start))

if __name__ == "__main__":
    application.run_polling()