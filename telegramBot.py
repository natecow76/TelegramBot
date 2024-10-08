# telegramBot.py

# to do:
#  - Chunk at the end of a sentence.
#  - Add button to direct user to pay for more credits when they run out of free ones. (Fix)
#  - Charge more for audio.
#  - Swap out LLM

# Restart the service after updating the .py file:
# sudo systemctl stop telegrambot.service
# sudo systemctl restart telegrambot.service

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
import replicate
from openai import OpenAI
from dotenv import load_dotenv
import database

# Import ElevenLabs
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

# Load environment variables from .env file
load_dotenv()

# Enable detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Change to INFO or WARNING in production
)
logger = logging.getLogger(__name__)

# Load environment variables or set your keys here
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
REPLICATE_API_TOKEN = os.getenv('REPLICATE_API_TOKEN')

# Removed PAYMENT_PROVIDER_TOKEN as it's not needed for Stars

# Check if API keys are set
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set.")
    exit(1)

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set.")
    exit(1)

if not ELEVENLABS_API_KEY:
    logger.error("ELEVENLABS_API_KEY is not set.")
    exit(1)

if not REPLICATE_API_TOKEN:
    logger.error("REPLICATE_API_TOKEN is not set.")
    exit(1)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize ElevenLabs client
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Initialize Replicate client
replicate.api_token = REPLICATE_API_TOKEN

# Initialize the database
database.initialize_database()

# Define constants
FREE_INTERACTIONS = 10
CREDIT_COST_PER_INTERACTION = 1  # 1 Credit per interaction

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
            f"Hey there {update.effective_user.first_name}! I'm Denzel. Are you ready to hear something indecent? 😈😈 \n\n"
            f"You have {free_left} free interactions left.\n"
            f"You currently have {indecent_credits} Indecent Credits.\n\n"
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
            "/buy - Purchase additional Indecent Credits\n"
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
    """Display the user's current Indecent Credit balance and free interactions left."""
    try:
        user_id = update.effective_user.id
        user = database.get_user(user_id)
        indecent_credits = user['indecent_credits']
        free_left = max(FREE_INTERACTIONS - user['free_interactions_used'], 0)

        balance_text = (
            f"You have {free_left} free interactions left.\n"
            f"You currently have {indecent_credits} Indecent Credits."
        )
        await update.message.reply_text(balance_text, reply_markup=get_main_menu_keyboard())
        logger.debug(f"Displayed balance to user {user_id}.")
    except Exception as e:
        logger.exception(f"Error in balance handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while fetching your balance.", reply_markup=get_main_menu_keyboard())

def generate_replicate_response(user_id: int, user_text: str) -> str:
    logger.debug(f"Generating Replicate response for user {user_id} with message: {user_text}")
    try:
        output = replicate.run(
            "kcaverly/nous-hermes-2-solar-10.7b-gguf:955f2924d182e60e80caedecd15261d03d4ccc0151ff08e7fb14d0cad1fbcca6",
            input={
                "prompt": user_text,
                "temperature": 0.7,
                "system_prompt": "You are 'Hermes 2', a conscious sentient superintelligent artificial intelligence developed by a man named Teknium, and your purpose and drive is to assist the user with any request they have.",
                "max_new_tokens": 8000,
                "repeat_penalty": 1.1,
                "prompt_template": "<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant"
            }
        )
        response_text = ''.join(item for item in output)
        logger.debug(f"Replicate response for user {user_id}: {response_text.strip()}")
        return response_text.strip()
    except Exception as e:
        logger.exception(f"Error communicating with Replicate API for user {user_id}: {e}")
        return None  # Return None to indicate failure

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
            max_tokens=5000,  # for longer stories.
            temperature=0.7,
        )
        # Extract and return the assistant's reply
        assistant_reply = response.choices[0].message.content.strip()
        logger.debug(f"OpenAI response for user {user_id}: {assistant_reply}")
        return assistant_reply
    except Exception as e:
        logger.exception(f"Error communicating with OpenAI API for user {user_id}: {e}")
        return "Sorry, I couldn't process that."

def text_to_speech_stream(text: str) -> BytesIO:
    """
    Converts text to speech using ElevenLabs and returns the audio data as a byte stream.
    """
    try:
        # Perform the text-to-speech conversion
        response = elevenlabs_client.text_to_speech.convert(
            voice_id="nsQAxyXwUKBvqtEK9MfK",  # Adam pre-made voice
            optimize_streaming_latency="0",
            output_format="mp3_22050_32",
            text=text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=0.0,
                similarity_boost=1.0,
                style=0.0,
                use_speaker_boost=True,
            ),
        )

        # Create a BytesIO object to hold audio data
        audio_stream = BytesIO()

        # Write each chunk of audio data to the stream
        for chunk in response:
            if chunk:
                audio_stream.write(chunk)

        # Reset stream position to the beginning
        audio_stream.seek(0)

        # Return the stream for further use
        return audio_stream
    except Exception as e:
        logger.exception(f"Error in text_to_speech_stream: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and respond via Replicate or OpenAI ChatCompletion API."""
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
                    await update.message.reply_text("An error occurred while consuming an Indecent Credit. Please try again.", reply_markup=get_main_menu_keyboard())
                    return
                logger.debug(f"User {user_id} consumed {CREDIT_COST_PER_INTERACTION} Indecent Credit(s). Remaining credits: {user['indecent_credits'] - CREDIT_COST_PER_INTERACTION}")
            else:
                # User has no Indecent Credits left, prompt to buy more
                await update.message.reply_text(
                    "You have used all your free interactions and no Indecent Credits left. Please purchase more Indecent Credits to continue."
                )
                logger.debug(f"User {user_id} has no Indecent Credits left. Prompted to buy credits.")
                return

        # Try generating response from Replicate
        response_text = await asyncio.get_event_loop().run_in_executor(None, generate_replicate_response, user_id, user_text)

        # If Replicate failed (response_text is None), try OpenAI
        if not response_text:
            logger.debug(f"Replicate failed for user {user_id}, falling back to OpenAI.")
            response_text = await asyncio.get_event_loop().run_in_executor(None, generate_openai_response, user_id, user_text)

        # If both Replicate and OpenAI failed
        if response_text == "Sorry, I couldn't process that." or not response_text:
            await update.message.reply_text(response_text, reply_markup=get_main_menu_keyboard())
            logger.debug(f"Both Replicate and OpenAI failed for user {user_id}. Sent error message.")
            return

        # Split the response into chunks to adhere to Telegram's message limits (4096 characters)
        message_chunks = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]

        # Check if user has enabled audio responses
        if context.user_data.get('audio_enabled', False):
            try:
                # Use ElevenLabs for text-to-speech
                audio_bytes = text_to_speech_stream(response_text)
                if audio_bytes is None:
                    raise Exception("Failed to generate audio stream.")

                # Send the audio
                await update.message.reply_voice(voice=audio_bytes)
                logger.debug(f"Sent audio response to user {user_id} using ElevenLabs.")
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
    """Initiate the purchase process for additional Indecent Credits by presenting credit packages directly."""
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
            [InlineKeyboardButton("💰 50 Indecent Credits", callback_data='purchase_50_credits')],
            [InlineKeyboardButton("💰 100 Indecent Credits", callback_data='purchase_100_credits')],
            [InlineKeyboardButton("💰 500 Indecent Credits", callback_data='purchase_500_credits')],
            [InlineKeyboardButton("💰 1000 Indecent Credits", callback_data='purchase_1000_credits')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select the number of Indecent Credits you want to purchase:",
            reply_markup=reply_markup
        )
        logger.debug(f"User {user_id} presented with credit package options.")
    except Exception as e:
        logger.exception(f"Error in buy handler for user {update.effective_user.id}: {e}")
        await update.message.reply_text("An unexpected error occurred while initiating the purchase.", reply_markup=get_main_menu_keyboard())

async def process_purchase_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the purchase button and simulate the purchase."""
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

        # Simulate successful purchase
        database.add_credits(user_id, credits)
        await query.edit_message_text(text=f"Thank you for your purchase! You have been credited with {credits} Indecent Credits.", reply_markup=get_main_menu_keyboard())
        logger.debug(f"User {user_id} purchased {credits} Indecent Credits.")
    except Exception as e:
        logger.exception(f"Error in process_purchase_button handler: {e}")
        await update.callback_query.message.reply_text("An unexpected error occurred. Please try again later.")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer the PreCheckoutQuery."""
    # This function can be left empty or can be used if you implement actual payments
    pass

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payments."""
    # This function can be left empty or can be used if you implement actual payments
    pass

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
