# telegramBot.py

# to do: 
#  - Chunk at the end of a sentence. 
#  - Add button to direct user to pay for more credits when they run out of free ones. (Fix)
#  - Charge more for audio. $1/minute? 
#  - Swap out LLM
#  - Swap out TTS engine 
#  - Host it somewhere

import logging
import os
import asyncio
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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

# Define the custom menu keyboard
def get_main_menu_keyboard():
    """Returns the main menu keyboard."""
    keyboard = [
        ['🏠 Home', '📚 Help'],
        ['💰 Buy Credits', '💳 Balance'],
        ['🎁 Free Credits', '🔊 Audio On/Off']  # Both buttons in the same row
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# Define menu options
MENU_OPTIONS = ['🏠 Home', '📚 Help', '💰 Buy Credits', '💳 Balance', '🎁 Free Credits', '🔊 Audio On/Off']

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message with the main menu when the /start command is issued."""
    try:
        user_id = update.effective_user.id
        user = database.get_user(user_id)
        free_left = max(FREE_INTERACTIONS - user['free_interactions_used'], 0)
        indecent_credits = user['indecent_credits']

        welcome_text = (
            f"Hello {update.effective_user.first_name}! Are you ready for some exciting stories? \n\n"
            f"You have {free_left} free interactions left.\n"
            f"You currently have {indecent_credits} Credits.\n\n"
            f"Use the menu below to navigate through my features."
        )

        await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard())
        logger.debug(f"Sent welcome message to user {user_id} with main menu.")
    except Exception as e:
        logger.exception(f"Error in start handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred. Please try again later.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message when the /help command is issued."""
    try:
        help_text = (
            "You can control me by using the menu below or by sending these commands:\n\n"
            "/start - Welcome message with main menu\n"
            "/help - This help message\n"
            "/audio - Toggle audio responses on/off\n"
            "/buy - Purchase additional Credits\n"
            "/balance - Check your current balance\n\n"
            "By default, I reply with text. Use /audio to receive voice messages."
        )
        await update.message.reply_text(help_text, reply_markup=get_main_menu_keyboard())
        logger.debug("Sent help message to user.")
    except Exception as e:
        logger.exception(f"Error in help_command handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while fetching help information.", reply_markup=get_main_menu_keyboard())

async def toggle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle audio responses for the user."""
    try:
        user_data = context.user_data
        audio_enabled = user_data.get('audio_enabled', False)
        user_data['audio_enabled'] = not audio_enabled
        status = "enabled" if user_data['audio_enabled'] else "disabled"
        await update.message.reply_text(f"Audio responses have been {status}.", reply_markup=get_main_menu_keyboard())
        logger.debug(f"Audio responses have been {status} for user {update.effective_user.id}.")
    except Exception as e:
        logger.exception(f"Error in toggle_audio handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while toggling audio.", reply_markup=get_main_menu_keyboard())

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the user's current Credit balance and free interactions left."""
    try:
        user_id = update.effective_user.id
        user = database.get_user(user_id)
        indecent_credits = user['indecent_credits']
        free_left = max(FREE_INTERACTIONS - user['free_interactions_used'], 0)

        balance_text = (
            f"You have {free_left} free interactions left.\n"
            f"You currently have {indecent_credits} Credits."
        )
        await update.message.reply_text(balance_text, reply_markup=get_main_menu_keyboard())
        logger.debug(f"Displayed balance to user {user_id}.")
    except Exception as e:
        logger.exception(f"Error in balance handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while fetching your balance.", reply_markup=get_main_menu_keyboard())

def generate_openai_response(user_id: int, user_text: str) -> str:
    """Generate a response from OpenAI's ChatCompletion API."""
    logger.debug(f"Generating OpenAI response for user {user_id} with message: {user_text}")
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # You can also use "gpt-4 or gpt-4o or gpt-4o-mini"
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_text}
            ],
            max_tokens=5000, #for longer stories. 
            temperature=0.7,
        )
        # Extract and return the assistant's reply
        assistant_reply = response.choices[0].message.content.strip()
        logger.debug(f"OpenAI response for user {user_id}: {assistant_reply}")
        return assistant_reply
    except Exception as e:
        logger.exception(f"Error communicating with OpenAI API for user {user_id}: {e}")
        return "Sorry, I couldn't process that."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and respond via OpenAI ChatCompletion API."""
    try:
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
            if user['indecent_credits'] >= CREDIT_COST_PER_INTERACTION:
                # Consume Indecent Credits
                success = database.consume_credit(user_id)
                if not success:
                    await update.message.reply_text("An error occurred while consuming a Credit. Please try again.", reply_markup=get_main_menu_keyboard())
                    return
                logger.debug(f"User {user_id} consumed {CREDIT_COST_PER_INTERACTION} Credit(s). Remaining credits: {user['indecent_credits'] - CREDIT_COST_PER_INTERACTION}")
            else:
                # User has no Indecent Credits left, prompt to buy more
                # This commented bit should have shown a button to buy more, but it wasn't working, so I cut it.
                #keyboard = [
                #    [InlineKeyboardButton("💰 Buy Indecent Credits", callback_data='buy_credits')]
                #]
                #reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "You have used all your free interactions and no Credits left. Please purchase more Credits to continue."
                )
                logger.debug(f"User {user_id} has no Credits left. Prompted to buy credits.")
                return

        # Generate response from OpenAI
        response_text = await asyncio.get_event_loop().run_in_executor(None, generate_openai_response, user_id, user_text)

        # Check if OpenAI returned an error message
        if response_text == "Sorry, I couldn't process that.":
            await update.message.reply_text(response_text, reply_markup=get_main_menu_keyboard())
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
                logger.exception(f"Error generating or sending audio response to user {user_id}: {e}")
                await update.message.reply_text("Sorry, I couldn't generate an audio response.", reply_markup=get_main_menu_keyboard())
        else:
            for chunk in message_chunks:
                await update.message.reply_text(chunk, reply_markup=get_main_menu_keyboard())
                logger.debug(f"Sent text response chunk to user {user_id}.")
    except Exception as e:
        logger.exception(f"Error in handle_message handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while processing your message.", reply_markup=get_main_menu_keyboard())

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiate the purchase process for additional Credits by presenting credit packages directly."""
    try:
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
            [InlineKeyboardButton("💰 50 Credits", callback_data='purchase_50_credits')],
            [InlineKeyboardButton("💰 100 Credits", callback_data='purchase_100_credits')],
            [InlineKeyboardButton("💰 500 Credits", callback_data='purchase_500_credits')],
            [InlineKeyboardButton("💰 1000 Credits", callback_data='purchase_1000_credits')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select the number of Credits you want to purchase:",
            reply_markup=reply_markup
        )
        logger.debug(f"User {user_id} presented with credit package options.")
    except Exception as e:
        logger.exception(f"Error in buy handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while initiating the purchase.", reply_markup=get_main_menu_keyboard())

async def process_purchase_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the purchase button and send the invoice."""
    try:
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

        # Calculate the amount in the smallest currency units (1 Indecent Credit = 1 XTR = 1 unit)
        amount = credits  # 1 Indecent Credit = 1 XTR = 1 unit

        # Create an invoice payload
        payload = f"purchase_{credits}_credits"

        # Define the price using LabeledPrice
        prices = [LabeledPrice(label=f"{credits} Credits", amount=amount)]

        # Send the invoice using Telegram Stars
        try:
            await context.bot.send_invoice(
                chat_id=user_id,
                title=f"Purchase {credits} Credits",
                description=f"Get {credits} Credits.",
                payload=payload,
                provider_token="",      # Replace with your provider token if needed
                currency="XTR",         # Telegram Stars currency code
                prices=prices,
                start_parameter=f"buy_{credits}_credits",
                need_name=False,        # Stars payments typically don't require user info
                need_phone_number=False,
                need_email=False,
                is_flexible=False,
            )
            logger.debug(f"Sent invoice to user {user_id} for {credits} Credits.")
        except Exception as e:
            logger.exception(f"Error sending invoice to user {user_id}: {e}")
            await query.edit_message_text(text="Sorry, an error occurred while processing your purchase. Please try again later.")
    except Exception as e:
        logger.exception(f"Error in process_purchase_button handler: {e}")
        await update.callback_query.message.reply_text("An unexpected error occurred. Please try again later.")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer the PreCheckoutQuery."""
    try:
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
    except Exception as e:
        logger.exception(f"Error in precheckout_callback handler: {e}")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payments."""
    try:
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
                database.add_credits(user_id, credits_purchased)
                await message.reply_text(f"Thank you for your purchase! You have been credited with {credits_purchased} Credits.", reply_markup=get_main_menu_keyboard())
                logger.debug(f"User {user_id} purchased {credits_purchased} Credits.")
            except ValueError:
                await message.reply_text("Payment received, but could not determine the purchase details.", reply_markup=get_main_menu_keyboard())
                logger.warning(f"User {user_id} sent a payment with invalid payload: {payload}")
        else:
            await message.reply_text("Payment received, but could not determine the purchase details.", reply_markup=get_main_menu_keyboard())
            logger.warning(f"User {user_id} sent a payment with invalid payload: {payload}")
    except Exception as e:
        logger.exception(f"Error in successful_payment_callback handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred after your payment. Please contact support.", reply_markup=get_main_menu_keyboard())

async def reset_interactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset the user's free interactions used."""
    try:
        user_id = update.effective_user.id
        database.update_user(user_id, free_interactions_used=0)
        await update.message.reply_text("Your free interactions have been reset to 10.", reply_markup=get_main_menu_keyboard())
        logger.debug(f"Reset free interactions for user {user_id}.")
    except Exception as e:
        logger.exception(f"Error in reset_interactions handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while resetting your interactions.", reply_markup=get_main_menu_keyboard())

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle menu button presses."""
    try:
        user_text = update.message.text
        user_id = update.effective_user.id
        logger.debug(f"Received menu button press from user {user_id}: {user_text}")

        if user_text == '🏠 Home':
            await start(update, context)
        elif user_text == '📚 Help':
            await help_command(update, context)
        elif user_text == '💰 Buy Credits':
            await buy(update, context)
        elif user_text == '💳 Balance':
            await balance(update, context)
        elif user_text == '🎁 Free Credits':  # Updated button label
            await reset_interactions(update, context)
        elif user_text == '🔊 Audio On/Off':  # Updated button label
            await toggle_audio(update, context)
        else:
            # Handle unexpected inputs
            await update.message.reply_text("Please choose an option from the menu below.", reply_markup=get_main_menu_keyboard())
            logger.debug(f"User {user_id} sent an unexpected input: {user_text}")
    except Exception as e:
        logger.exception(f"Error in menu_handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while processing your menu selection.", reply_markup=get_main_menu_keyboard())

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all exceptions."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Notify the user about the error
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "An unexpected error occurred. Please try again later."
            )
        except Exception as e:
            logger.exception(f"Failed to send error message to user: {e}")

def main() -> None:
    """Start the bot."""
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Define menu options regex filter
    menu_filter = filters.Regex(f"^({'|'.join(MENU_OPTIONS)})$")

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("audio", toggle_audio))
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("reset", reset_interactions))  # Optional command

    # Register message handlers
    application.add_handler(MessageHandler(menu_filter, menu_handler))  # Handle menu button presses
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, handle_message))  # Handle regular messages

    # Register other handlers
    application.add_handler(CallbackQueryHandler(process_purchase_button, pattern='^purchase_\\d+_credits$'))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # Register the error handler
    application.add_error_handler(error_handler)

    # Start the Bot
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()