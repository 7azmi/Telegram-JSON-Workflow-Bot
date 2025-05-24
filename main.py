# main.py - Updated

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler
import module # Import our workflow module

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Replace with your actual bot token
BOT_TOKEN = "7959455833:AAFuOGqw_PGOBVg-VPyvsHPPabWc_dTmcGw" # !!! REMEMBER TO REPLACE THIS !!!
# Path to the JSON workflow file
WORKFLOW_FILE = "workflow_config.json" # Assuming the sample JSON is saved here

# --- Load Workflow ---
workflow_data = module.load_workflow_data(WORKFLOW_FILE)
if not workflow_data:
    logger.error("Failed to load workflow data. Exiting.")
    exit()

workflow_manager = module.WorkflowManager(workflow_data)

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the workflow."""
    chat_id = update.effective_chat.id
    logger.info(f"User {chat_id} started the workflow.")

    # Reset user state and get the initial step keyboard and text
    workflow_manager.reset_user_state(chat_id)
    reply_markup, text = workflow_manager.generate_keyboard_and_text(chat_id)

    if reply_markup and text:
        # Send the initial message
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=chat_id, text="Error starting workflow.")

async def show_selections(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the user's current selections (for debugging/demonstration)."""
    chat_id = update.effective_chat.id
    selections = workflow_manager.get_user_selections(chat_id)
    if selections:
        text = "Your current selections:\n"
        for step, value in selections.items():
            text += f"- {step}: {value}\n"
    else:
        text = "No selections made yet."

    await context.bot.send_message(chat_id=chat_id, text=text)

# --- Callback Query Handler ---

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button clicks from the inline keyboard."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    # Corrected: Get chat_id from query.message
    chat_id = query.message.chat.id
    callback_data = query.data
    logger.info(f"User {chat_id} clicked button with data: {callback_data}")

    # Process the callback data using the WorkflowManager
    # handle_callback_query now returns the step key to render *after* processing
    next_step_key, current_step_key_before_change, processed_value, is_workflow_end = workflow_manager.handle_callback_query(chat_id, callback_data)

    if is_workflow_end:
        # Workflow finished
        final_selections = workflow_manager.get_user_selections(chat_id)
        summary_text = "Workflow completed! Here are your selections:\n"
        for step, value in final_selections.items():
             summary_text += f"- {step}: {value}\n"
        # Optionally reset state after showing summary if you want a clean start next time
        # workflow_manager.reset_user_state(chat_id)

        # Edit the message to show the summary and remove the keyboard
        await query.edit_message_text(text=summary_text, reply_markup=None)
        logger.info(f"User {chat_id} workflow completed.")

    else:
        # Workflow continues or user stayed on same step (radio/checkbox/toggle/manual completion step)
        # Generate the keyboard and text for the step determined by handle_callback_query
        reply_markup, text = workflow_manager.generate_keyboard_and_text(chat_id)

        if reply_markup and text:
             # Edit the message to update the keyboard and text for the next/current step
             try:
                 # Check if the message content actually changed to avoid API errors
                 # This is a basic check, a more robust check might compare reply_markup and text
                 if query.message.reply_markup != reply_markup or query.message.text != text:
                    await query.edit_message_text(text=text, reply_markup=reply_markup)
                    logger.debug(f"User {chat_id}: Edited message for step '{workflow_manager._get_user_state(chat_id)['current_step']}'.")
                 else:
                    logger.debug(f"User {chat_id}: Message content unchanged for step '{workflow_manager._get_user_state(chat_id)['current_step']}'. No edit needed.")

             except Exception as e:
                 logger.warning(f"User {chat_id}: Failed to edit message: {e}. Message might be too old or not modified.")
                 # As a fallback, you could send a new message, but be aware of chat clutter.
                 # await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        elif text:
             # Only text changed (less likely with keyboard-driven steps)
             await query.edit_message_text(text=text)
             logger.debug(f"User {chat_id}: Edited message text.")
        else:
             # Should ideally not happen if generate_keyboard_and_text works correctly for a valid step_key
             logger.error(f"User {chat_id}: generate_keyboard_and_text returned None for step '{workflow_manager._get_user_state(chat_id)['current_step']}'.")


# --- Main Application Setup ---

def main():
    """Runs the bot."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("selections", show_selections)) # Optional: for debugging

    # Add callback query handler to catch all button clicks
    application.add_handler(CallbackQueryHandler(handle_button_click))

    # Run the bot
    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()