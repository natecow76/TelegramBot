# bot.py

import logging
import os
import asyncio
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    SuccessfulPayment,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI
from gtts import gTTS
from dotenv import load_dotenv
import database

# Load environment variables from .env file
load_dotenv()

# Enable detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Change to INFO or WARNING in production
)
logger = logging.getLogger(__name__)

# Load environment variables or set your keys here
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or 'YOUR_TELEGRAM_BOT_TOKEN'
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') or 'YOUR_OPENAI_API_KEY'
PAYMENT_PROVIDER_TOKEN = os.getenv('PAYMENT_PROVIDER_TOKEN') or 'YOUR_PAYMENT_PROVIDER_TOKEN'  # Stars Provider Token

# Check if API keys are set
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set.")
    exit(1)

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set.")
    exit(1)

if not PAYMENT_PROVIDER_TOKEN:
    logger.error("PAYMENT_PROVIDER_TOKEN is not set.")
    exit(1)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize the database
database.initialize_database()

# Define constants
FREE_INTERACTIONS = 10
STAR_COST_PER_INTERACTION = 1  # 1 star per interaction

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the /start command is issued."""
    user_id = update.effective_user.id
    user = database.get_user(user_id)
    stars_remaining = user['stars']
    free_left = max(FREE_INTERACTIONS - user['free_interactions_used'], 0)

    welcome_text = (
        f"Hello! I'm ChatGPT Bot.\n\n"
        f"You have {free_left} free interactions left.\n"
        f"You currently have {stars_remaining} stars.\n\n"
        f"Use /audio to toggle audio responses on/off.\n"
        f"Use /buy to purchase additional stars.\n"
        f"Use /balance to check your current balance."
    )
    await update.message.reply_text(welcome_text)
    logger.debug(f"Sent welcome message to user {user_id}.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message when the /help command is issued."""
    help_text = (
        "You can control me by sending these commands:\n\n"
        "/start - Welcome message\n"
        "/help - This help message\n"
        "/audio - Toggle audio responses on/off\n"
        "/buy - Purchase additional stars\n"
        "/balance - Check your current stars and free interactions\n\n"
        "By default, I reply with text. Use /audio to receive voice messages."
    )
    await update.message.reply_text(help_text)
    logger.debug("Sent help message to user.")

async def toggle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle audio responses for the user."""
    user_data = context.user_data
    audio_enabled = user_data.get('audio_enabled', False)
    user_data['audio_enabled'] = not audio_enabled
    status = "enabled" if user_data['audio_enabled'] else "disabled"
    await update.message.reply_text(f"Audio responses have been {status}.")
    logger.debug(f"Audio responses have been {status} for user {update.effective_user.id}.")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the user's current star balance and free interactions left."""
    user_id = update.effective_user.id
    user = database.get_user(user_id)
    stars_remaining = user['stars']
    free_left = max(FREE_INTERACTIONS - user['free_interactions_used'], 0)

    balance_text = (
        f"You have {free_left} free interactions left.\n"
        f"You currently have {stars_remaining} stars."
    )
    await update.message.reply_text(balance_text)
    logger.debug(f"Displayed balance to user {user_id}.")

def generate_openai_response(user_id: int, user_text: str) -> str:
    """Generate a response from OpenAI's ChatCompletion API."""
    logger.debug(f"Generating OpenAI response for user {user_id} with message: {user_text}")
    try:
        response = client.chat.completions.create(
            model="gpt-4",  # You can also use "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_text}
            ],
            max_tokens=500,
            temperature=0.7,
        )
        # Extract and return the assistant's reply
        assistant_reply = response.choices[0].message.content.strip()
        logger.debug(f"OpenAI response for user {user_id}: {assistant_reply}")
        return assistant_reply
    except Exception as e:
        logger.exception(f"Error communicating with OpenAI API for user {user_id}.")
        return "Sorry, I couldn't process that."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and respond via OpenAI ChatCompletion API."""
    user_text = update.message.text
    user_id = update.effective_user.id
    logger.debug(f"Received message from user {user_id}: {user_text}")

    user = database.get_user(user_id)
    logger.debug(f"User data: {user}")

    # Check if user has free interactions left
    if user['free_interactions_used'] < FREE_INTERACTIONS:
        # Increment free interactions used
        database.increment_free_interactions(user_id)
        logger.debug(f"User {user_id} has free interactions remaining.")
    else:
        # Check if user has enough stars
        if user['stars'] >= STAR_COST_PER_INTERACTION:
            # Consume stars
            success = database.consume_star(user_id)
            if not success:
                await update.message.reply_text("An error occurred while consuming a star. Please try again.")
                return
            logger.debug(f"User {user_id} consumed {STAR_COST_PER_INTERACTION} star(s). Remaining stars: {user['stars'] - STAR_COST_PER_INTERACTION}")
        else:
            # User has no stars left, prompt to buy more
            keyboard = [
                [InlineKeyboardButton("Buy Stars", callback_data='buy_stars')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "You have used all your free interactions and no stars left. Please purchase more stars to continue.",
                reply_markup=reply_markup
            )
            logger.debug(f"User {user_id} has no stars left. Prompted to buy stars.")
            return

    # Generate response from OpenAI
    response_text = await asyncio.get_event_loop().run_in_executor(None, generate_openai_response, user_id, user_text)

    # Check if OpenAI returned an error message
    if response_text == "Sorry, I couldn't process that.":
        await update.message.reply_text(response_text)
        logger.debug(f"Sent error message to user {user_id}.")
        return

    # Split the response into chunks to adhere to Telegram's message limits (4096 characters)
    message_chunks = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]

    # Check if user has enabled audio responses
    if context.user_data.get('audio_enabled', False):
        try:
            tts = gTTS(text=response_text, lang='en')
            audio_bytes = BytesIO()
            tts.write_to_fp(audio_bytes)
            audio_bytes.seek(0)

            # Send the audio
            await update.message.reply_voice(voice=audio_bytes)
            logger.debug(f"Sent audio response to user {user_id}.")
        except Exception as e:
            logger.exception(f"Error generating or sending audio response to user {user_id}.")
            await update.message.reply_text("Sorry, I couldn't generate an audio response.")
    else:
        for chunk in message_chunks:
            await update.message.reply_text(chunk)
            logger.debug(f"Sent text response chunk to user {user_id}.")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiate the purchase process for additional stars."""
    keyboard = [
        [InlineKeyboardButton("Buy Stars", callback_data='buy_stars')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Click the button below to purchase stars:", reply_markup=reply_markup)
    logger.debug(f"User {update.effective_user.id} initiated purchase.")

async def handle_buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the Buy Stars button press and present star package options."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    logger.debug(f"User {user_id} clicked the Buy Stars button.")

    # Define star packages
    star_packages = {
        'purchase_10_stars': {'stars': 10, 'price': 100},    # 10 stars for 100 cents ($1.00)
        'purchase_50_stars': {'stars': 50, 'price': 500},    # 50 stars for 500 cents ($5.00)
        'purchase_100_stars': {'stars': 100, 'price': 1000}, # 100 stars for 1000 cents ($10.00)
    }

    # Present star package options
    keyboard = [
        [InlineKeyboardButton("10 Stars - $1.00", callback_data='purchase_10_stars')],
        [InlineKeyboardButton("50 Stars - $5.00", callback_data='purchase_50_stars')],
        [InlineKeyboardButton("100 Stars - $10.00", callback_data='purchase_100_stars')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="Select the number of stars you want to purchase:", reply_markup=reply_markup)
    logger.debug(f"User {user_id} selected a star package.")

async def process_purchase_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the purchase button and send the invoice."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # Determine the number of stars based on the button pressed
    if data == 'purchase_10_stars':
        stars = 10
        amount = 100  # Amount in cents ($1.00)
    elif data == 'purchase_50_stars':
        stars = 50
        amount = 500  # $5.00
    elif data == 'purchase_100_stars':
        stars = 100
        amount = 1000  # $10.00
    else:
        await query.edit_message_text(text="Invalid selection.")
        logger.warning(f"User {user_id} made an invalid purchase selection: {data}")
        return

    # Create an invoice payload
    payload = f"purchase_{stars}_stars"

    # Send the invoice using Telegram Stars
    try:
        await context.bot.send_invoice(
            chat_id=user_id,
            title=f"Purchase {stars} Stars",
            description=f"Get {stars} stars for ${amount / 100:.2f}.",
            payload=payload,
            provider_token=PAYMENT_PROVIDER_TOKEN,  # Telegram Stars provider token
            currency="USD",
            prices=[{
                'label': f"{stars} Stars",
                'amount': amount  # amount in cents
            }],
            start_parameter=f"buy_{stars}_stars",
            need_name=True,
            need_phone_number=False,
            need_email=False,
            is_flexible=False,
        )
        logger.debug(f"Sent invoice to user {user_id} for {stars} stars.")
    except Exception as e:
        logger.exception(f"Error sending invoice to user {user_id}.")
        await query.edit_message_text(text="Sorry, an error occurred while processing your purchase. Please try again later.")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer the PreCheckoutQuery."""
    query = update.pre_checkout_query
    logger.debug(f"Received PreCheckoutQuery from user {query.from_user.id}: {query.invoice_payload}")

    # Here, you can perform any necessary checks before confirming the payment
    # For simplicity, we'll approve all pre-checkouts
    try:
        await query.answer(ok=True)
        logger.debug(f"PreCheckoutQuery approved for user {query.from_user.id}.")
    except Exception as e:
        logger.exception(f"Error answering PreCheckoutQuery for user {query.from_user.id}.")
        await query.answer(ok=False, error_message="An error occurred. Please try again.")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payments."""
    message = update.message
    successful_payment: SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id
    logger.debug(f"Received successful payment from user {user_id}: {successful_payment}")

    # Extract the payload to determine the number of stars purchased
    payload = successful_payment.invoice_payload
    # Assuming payload is in the format "purchase_{stars}_stars"
    if payload.startswith("purchase_") and payload.endswith("_stars"):
        try:
            stars_purchased = int(payload.split('_')[1])
            database.add_stars(user_id, stars_purchased)
            await message.reply_text(f"Thank you for your purchase! You have been credited with {stars_purchased} stars.")
            logger.debug(f"User {user_id} purchased {stars_purchased} stars.")
        except ValueError:
            await message.reply_text("Payment received, but could not determine the purchase details.")
            logger.warning(f"User {user_id} sent a payment with invalid payload: {payload}")
    else:
        await message.reply_text("Payment received, but could not determine the purchase details.")
        logger.warning(f"User {user_id} sent a payment with invalid payload: {payload}")

def main() -> None:
    """Start the bot."""
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("audio", toggle_audio))
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_buy_button, pattern='^buy_stars$'))
    application.add_handler(CallbackQueryHandler(process_purchase_button, pattern='^purchase_\d+_stars$'))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # Start the Bot
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
