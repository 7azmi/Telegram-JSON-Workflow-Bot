# main.py - Streamlined Interface

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
import inline_workflow_manager # Import our workflow module
import json # For pretty printing user_data
from telegram.helpers import escape_markdown # Import escaping utility

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Replace with your actual bot token
BOT_TOKEN = "Your Token" # !!! REMEMBER TO REPLACE THIS !!!
# Path to the JSON workflow file
WORKFLOW_FILE = "workflow_config.json" # Assuming the sample JSON is saved here

# --- Initialize Workflow Manager ---
# WorkflowManager now loads the data itself
workflow_manager = inline_workflow_manager.InlineWorkflowManager(WORKFLOW_FILE)

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the workflow."""
    chat_id = update.effective_chat.id
    logger.info(f"User {chat_id} started the workflow.")

    # Call the manager's start method
    reply_markup, text = workflow_manager.start_workflow(context)

    if reply_markup is not None and text is not None: # Check if manager returned UI
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='MarkdownV2')
    elif text is not None: # Manager might return only error text on init failure
         await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='MarkdownV2')
    else:
         # Should ideally not happen if text is returned on init failure
         await context.bot.send_message(chat_id=chat_id, text=escape_markdown("An unexpected error occurred starting the workflow.", version=2), parse_mode='MarkdownV2')


async def show_selections(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the user's current selections (for debugging/demonstration)."""
    chat_id = update.effective_chat.id
    selections = workflow_manager.get_user_selections(context)

    # Log user data for debugging
    logger.info(f"User {chat_id} context.user_data: {json.dumps(context.user_data, indent=2)}")


    if selections:
        # Escape the introductory text, JSON dump should be fine in ```json block
        intro_text = escape_markdown("Your current selections:", version=2)
        selections_json_str = json.dumps(selections, indent=2)

        text = f"{intro_text}\n```json\n{selections_json_str}\n```"
    else:
        text = escape_markdown("No selections made yet.", version=2)

    # Send with MarkdownV2 parse mode
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='MarkdownV2')


# --- Callback Query Handler ---

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button clicks from the inline keyboard."""
    query = update.callback_query
    # Always answer the query, regardless of processing outcome
    await query.answer()

    chat_id = query.message.chat.id
    callback_data = query.data
    logger.info(f"User {chat_id} clicked button with data: {callback_data}")

    # Call the manager's method to process the click and get the response UI/text
    response_text, reply_markup, is_final_message = workflow_manager.process_callback_and_get_response(context, callback_data)

    # Log user data after processing callback
    logger.info(f"User {chat_id} context.user_data AFTER callback: {json.dumps(context.user_data, indent=2)}")


    # Based on the response from the manager, edit the message
    if is_final_message:
        # Workflow finished or encountered a critical error ending the workflow
        try:
            await query.edit_message_text(text=response_text, reply_markup=reply_markup, parse_mode='MarkdownV2')
            logger.info(f"User {chat_id}: Final/Error message edited.")
        except Exception as e:
            logger.warning(f"User {chat_id}: Failed to edit message to show final/error state: {e}. Sending new message instead.")
            # Fallback: send a new message. Ensure parse_mode is correct.
            await context.bot.send_message(chat_id=chat_id, text=response_text, reply_markup=reply_markup, parse_mode='MarkdownV2')

    else:
        # Workflow is ongoing (either moved to next step, stayed on current, or got validation error)
        # response_text will contain the description or error message (already escaped)
        # reply_markup will contain the keyboard for the next/current step

        if reply_markup is not None: # If there is a keyboard to show
             try:
                 # Edit the message to update the keyboard and text
                 await query.edit_message_text(text=response_text, reply_markup=reply_markup, parse_mode='MarkdownV2')
                 logger.debug(f"User {chat_id}: Edited message for next step.")
             except Exception as e:
                 logger.warning(f"User {chat_id}: Failed to edit message for next step (might not be modified or too old): {e}.")
                 # Optional fallback: send a new message.
                 # await context.bot.send_message(chat_id=chat_id, text=response_text, reply_markup=reply_markup, parse_mode='MarkdownV2')
        else: # If no keyboard is returned (unlikely in this design unless a step has no buttons)
              try:
                 # Edit message text only, removing the keyboard if it was present
                 await query.edit_message_text(text=response_text, reply_markup=None, parse_mode='MarkdownV2')
                 logger.debug(f"User {chat_id}: Edited message text only.")
              except Exception as e:
                 logger.warning(f"User {chat_id}: Failed to edit message text only: {e}.")
                 # Fallback: send a new message
                 await context.bot.send_message(chat_id=chat_id, text=response_text, parse_mode='MarkdownV2')


# --- Main Application Setup ---

def main():
    """Runs the bot."""
    # Check if workflow manager initialized successfully
    if not workflow_manager.is_initialized:
        logger.error("Workflow manager failed to load data. Bot cannot start.")
        exit()

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