# buybot.py

import logging
import os
import asyncio
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    SuccessfulPayment,
    LabeledPrice,
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
# Removed PAYMENT_PROVIDER_TOKEN as it's not needed for Stars

# Check if API keys are set
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set.")
    exit(1)

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set.")
    exit(1)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize the database
database.initialize_database()

# Define constants
FREE_INTERACTIONS = 10
CREDIT_COST_PER_INTERACTION = 1  # 1 Indecent Credit per interaction

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the /start command is issued."""
    user_id = update.effective_user.id
    user = database.get_user(user_id)
    free_left = max(FREE_INTERACTIONS - user['free_interactions_used'], 0)
    indecent_credits = user['stars']

    welcome_text = (
        f"Hello! I'm ChatGPT Bot.\n\n"
        f"You have {free_left} free interactions left.\n"
        f"You currently have {indecent_credits} Indecent Credits.\n\n"
        f"Use /audio to toggle audio responses on/off.\n"
        f"Use /buy to purchase additional Indecent Credits.\n"
        f"Use /balance to check your current balance.\n\n"
        f"**Note:** 1 Indecent Credit equals 1 Star in Telegram."
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
        "/buy - Purchase additional Indecent Credits\n"
        "/balance - Check your current balance\n\n"
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
    """Display the user's current Indecent Credit balance and free interactions left."""
    user_id = update.effective_user.id
    user = database.get_user(user_id)
    free_left = max(FREE_INTERACTIONS - user['free_interactions_used'], 0)

    indecent_credits = user['stars'] + free_left


    balance_text = (
        #f"You have {free_left} free interactions left.\n"
        f"You currently have {indecent_credits} Indecent Credits."
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
        # Check if user has enough Indecent Credits
        if user['stars'] >= CREDIT_COST_PER_INTERACTION:
            # Consume Indecent Credits
            success = database.consume_star(user_id)
            if not success:
                await update.message.reply_text("An error occurred while consuming an Indecent Credit. Please try again.")
                return
            logger.debug(f"User {user_id} consumed {CREDIT_COST_PER_INTERACTION} Indecent Credit(s). Remaining credits: {user['stars'] - CREDIT_COST_PER_INTERACTION}")
        else:
            # User has no Indecent Credits left, prompt to buy more
            keyboard = [
                [InlineKeyboardButton("Buy Indecent Credits", callback_data='buy_credits')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "You have used all your free interactions and no Indecent Credits left. Please purchase more Indecent Credits to continue.",
                reply_markup=reply_markup
            )
            logger.debug(f"User {user_id} has no Indecent Credits left. Prompted to buy credits.")
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
    """Initiate the purchase process for additional Indecent Credits by presenting credit packages directly."""
    user_id = update.effective_user.id
    logger.debug(f"User {user_id} initiated purchase.")

    # Define Indecent Credit packages without referencing currency
    credit_packages = {
        'purchase_50_credits': {'credits': 50},
        'purchase_100_credits': {'credits': 100},
        'purchase_500_credits': {'credits': 500},
        'purchase_1000_credits': {'credits': 1000},
    }

    # Present credit package options directly
    keyboard = [
        [InlineKeyboardButton("50 Indecent Credits", callback_data='purchase_50_credits')],
        [InlineKeyboardButton("100 Indecent Credits", callback_data='purchase_100_credits')],
        [InlineKeyboardButton("500 Indecent Credits", callback_data='purchase_500_credits')],
        [InlineKeyboardButton("1000 Indecent Credits", callback_data='purchase_1000_credits')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Select the number of Indecent Credits you want to purchase:",
        reply_markup=reply_markup
    )
    logger.debug(f"User {user_id} presented with credit package options.")

async def process_purchase_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the purchase button and send the invoice."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # Determine the number of Indecent Credits based on the button pressed
    if data == 'purchase_50_credits':
        credits = 50
    elif data == 'purchase_100_credits':
        credits = 100
    elif data == 'purchase_500_credits':
        credits = 500
    elif data == 'purchase_1000_credits':
        credits = 1000
    else:
        await query.edit_message_text(text="Invalid selection.")
        logger.warning(f"User {user_id} made an invalid purchase selection: {data}")
        return

    # Calculate the amount in the smallest currency units (1 Indecent Credit = 1 XTR = 100 units)
    amount = credits #* 100  # 1 Indecent Credit = 1 XTR = 100 units

    # Create an invoice payload
    payload = f"purchase_{credits}_credits"

    # Define the price using LabeledPrice
    prices = [LabeledPrice(label=f"{credits} Indecent Credits", amount=amount)]

    # Send the invoice using Telegram Stars
    try:
        await context.bot.send_invoice(
            chat_id=user_id,
            title=f"Purchase {credits} Indecent Credits",
            description=f"Get {credits} Indecent Credits.",
            payload=payload,
            provider_token="",      # Empty token for digital goods (Stars)
            currency="XTR",         # Telegram Stars currency code
            prices=prices,
            start_parameter=f"buy_{credits}_credits",
            need_name=False,        # Stars payments typically don't require user info
            need_phone_number=False,
            need_email=False,
            is_flexible=False,
        )
        logger.debug(f"Sent invoice to user {user_id} for {credits} Indecent Credits.")
    except Exception as e:
        logger.exception(f"Error sending invoice to user {user_id}: {e}")
        await query.edit_message_text(text="Sorry, an error occurred while processing your purchase. Please try again later.")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer the PreCheckoutQuery."""
    query = update.pre_checkout_query
    logger.debug(f"Received PreCheckoutQuery from user {query.from_user.id}: {query.invoice_payload}")

    # Verify the payload format
    if not (query.invoice_payload.startswith("purchase_") and query.invoice_payload.endswith("_credits")):
        await query.answer(ok=False, error_message="Invalid purchase payload.")
        logger.warning(f"User {query.from_user.id} sent an invalid payload: {query.invoice_payload}")
        return

    # Approve the pre-checkout query
    try:
        await query.answer(ok=True)
        logger.debug(f"PreCheckoutQuery approved for user {query.from_user.id}.")
    except Exception as e:
        logger.exception(f"Error answering PreCheckoutQuery for user {query.from_user.id}: {e}")
        await query.answer(ok=False, error_message="An error occurred. Please try again.")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payments."""
    message = update.message
    successful_payment: SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id
    logger.debug(f"Received successful payment from user {user_id}: {successful_payment}")

    # Extract the payload to determine the number of Indecent Credits purchased
    payload = successful_payment.invoice_payload
    # Assuming payload is in the format "purchase_{credits}_credits"
    if payload.startswith("purchase_") and payload.endswith("_credits"):
        try:
            credits_purchased = int(payload.split('_')[1])
            database.add_stars(user_id, credits_purchased)
            await message.reply_text(f"Thank you for your purchase! You have been credited with {credits_purchased} Indecent Credits.")
            logger.debug(f"User {user_id} purchased {credits_purchased} Indecent Credits.")
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
    # Removed the CallbackQueryHandler for 'buy_stars' as it's no longer needed
    application.add_handler(CallbackQueryHandler(process_purchase_button, pattern='^purchase_\d+_credits$'))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # Start the Bot
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
