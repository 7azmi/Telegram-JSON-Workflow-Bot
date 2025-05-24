# module.py - Final Updates

import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Emojis
RADIO_UNSELECTED = "🔘"
RADIO_SELECTED = "🟢"
CHECKBOX_UNSELECTED = "⬜"
CHECKBOX_SELECTED = "✅"
TOGGLE_OFF = "🔴"
TOGGLE_ON = "🟢"
BACK_EMOJI = "⬅️"
DONE_EMOJI = "✅" # Or "▶️" "➡️" for next


class WorkflowManager:
    """
    Manages a multi-step inline button workflow defined by a JSON structure.
    Handles stateful buttons (radio, checkbox, toggle) and navigation (forward, back, skip, manual completion, finish).
    """

    def __init__(self, workflow_data):
        """
         Initializes the WorkflowManager.

        Args:
            workflow_data (dict): The parsed dictionary from the workflow JSON.
                                  Expected format: { "workflow_name": { "step1_key": { ... }, "step2_key": { ... }, ... } }
        """
        if not isinstance(workflow_data, dict) or not workflow_data:
            raise ValueError("workflow_data must be a non-empty dictionary.")
        if len(workflow_data) != 1:
             logger.warning("Workflow data contains multiple top-level keys. Using the first one found.")

        self.workflow_name = list(workflow_data.keys())[0]
        self.workflow_steps = workflow_data[self.workflow_name]
        self._step_keys = list(self.workflow_steps.keys()) # Ordered list of step keys (Python 3.7+ guarantees order)

        # Dictionary to store user states { chat_id: { current_step: 'step_key', selections: { step_key: value | [values] | state_dict } } }
        # In-memory state - use a database for production.
        self._user_states = {}
        logger.info(f"WorkflowManager initialized for workflow: '{self.workflow_name}' with steps: {self._step_keys}")

    def _get_step_config(self, step_key):
        """Retrieves the configuration for a given step key."""
        return self.workflow_steps.get(step_key)

    def get_initial_step_key(self):
        """Returns the key for the first step in the workflow."""
        if not self._step_keys:
            return None
        return self._step_keys[0]

    def _get_next_step_key(self, current_step_key, skip_steps=0):
        """Calculates the next step key after the current one, considering skips."""
        try:
            current_index = self._step_keys.index(current_step_key)
            next_index = current_index + 1 + skip_steps
            if 0 <= next_index < len(self._step_keys):
                return self._step_keys[next_index]
            else:
                return None # Indicates end of workflow
        except ValueError:
            logger.error(f"Current step key '{current_step_key}' not found in workflow keys.")
            return None

    def _get_previous_step_key(self, current_step_key):
         """Calculates the previous step key."""
         try:
             current_index = self._step_keys.index(current_step_key)
             prev_index = current_index - 1
             if prev_index >= 0:
                 return self._step_keys[prev_index]
             else:
                 return None # Indicates no previous step (start of workflow)
         except ValueError:
             logger.error(f"Current step key '{current_step_key}' not found in workflow keys.")
             return None

    def _get_user_state(self, chat_id):
        """Gets or initializes the state for a user."""
        if chat_id not in self._user_states:
            self._user_states[chat_id] = {
                'current_step': self.get_initial_step_key(),
                'selections': {} # Stores selections per step key
            }
            logger.debug(f"Initialized state for new user {chat_id}")
        return self._user_states[chat_id]

    def _set_user_step(self, chat_id, step_key):
        """Sets the user's current step."""
        state = self._get_user_state(chat_id)
        state['current_step'] = step_key
        logger.debug(f"User {chat_id} current step set to: {step_key}")

    def _get_selection_value(self, chat_id, step_key):
        """Retrieves the recorded selection(s) for a specific step."""
        state = self._get_user_state(chat_id)
        return state['selections'].get(step_key)

    def _update_selection(self, chat_id, step_key, button_config):
        """Updates the user's selection for a step based on button type (excluding navigation types)."""
        selection_value = button_config.get('value')
        button_type = button_config.get('type')

        # Only update state for buttons that represent a selection, not just navigation
        if button_type in [None, 'radio', 'checkbox', 'toggle', 'skip']: # Include skip as it has a value like 'any'
             state = self._get_user_state(chat_id)
             current_selection = state['selections'].get(step_key)

             if button_type is None or button_type == 'radio' or button_type == 'skip':
                  # Default, Radio, Skip buttons store a single value for the step
                  state['selections'][step_key] = selection_value
                  logger.debug(f"User {chat_id}: Selection button '{button_config.get('buttonName')}' ({button_type}) pressed. Value '{selection_value}' recorded for step '{step_key}'.")

             elif button_type == 'checkbox':
                 # Checkboxes store a list of selected values
                 if current_selection is None:
                     current_selection = []
                 elif not isinstance(current_selection, list):
                      current_selection = []
                      logger.warning(f"User {chat_id}: State for step '{step_key}' was not a list for checkbox. Resetting.")

                 if selection_value in current_selection:
                     current_selection.remove(selection_value)
                     logger.debug(f"User {chat_id}: Checkbox '{button_config.get('buttonName')}' deselected. Value '{selection_value}' removed from step '{step_key}'.")
                 else:
                     current_selection.append(selection_value)
                     logger.debug(f"User {chat_id}: Checkbox '{button_config.get('buttonName')}' selected. Value '{selection_value}' added to step '{step_key}'.")

                 state['selections'][step_key] = current_selection

             elif button_type == 'toggle':
                 # Toggle buttons store a boolean state associated with their value in a dict
                 if current_selection is None or not isinstance(current_selection, dict):
                      current_selection = {} # Initialize state for toggles

                 # Toggle the state for the specific value
                 current_state_for_value = current_selection.get(selection_value, button_config.get('initialState', False))
                 current_selection[selection_value] = not current_state_for_value
                 logger.debug(f"User {chat_id}: Toggle '{button_config.get('buttonName')}' flipped to {current_selection[selection_value]}.")
                 state['selections'][step_key] = current_selection

             # No update needed for 'done', 'back', 'finish' actions here

    def generate_keyboard_and_text(self, chat_id):
        """
        Generates the InlineKeyboardMarkup and message text for the user's current step.
        Includes emojis for stateful buttons and 'Done/Next', 'Go Back', 'Finish' buttons as configured.

        Args:
            chat_id (int): The user's chat ID.

        Returns:
            tuple: (InlineKeyboardMarkup, str) or (None, str) if the step is not found or error.
        """
        state = self._get_user_state(chat_id)
        current_step_key = state['current_step']
        step_config = self._get_step_config(current_step_key)

        if not step_config:
            logger.error(f"Could not find configuration for step: {current_step_key}. Workflow may have ended unexpectedly.")
            self.reset_user_state(chat_id) # Consider resetting on critical error
            return None, "An internal error occurred. Please try starting again with /start." # Return None for keyboard

        keyboard_rows = []
        user_selections_for_step = self._get_selection_value(chat_id, current_step_key)
        step_completion_type = step_config.get('completionType', 'auto') # Default to auto

        for row_index, row in enumerate(step_config.get('options', [])):
            button_row = []
            for button_index, button_config in enumerate(row):
                button_text = button_config['buttonName']
                button_value = button_config.get('value')
                button_type = button_config.get('type') # Default is None

                # Modify button text with emoji based on state and type
                if button_type == 'radio':
                    # For radio, check if the current selection for the step matches this button's value
                    # Note: This assumes a single radio choice is stored per step key
                    if user_selections_for_step == button_value:
                         button_text = f"{RADIO_SELECTED} {button_text}"
                    else:
                         button_text = f"{RADIO_UNSELECTED} {button_text}"
                elif button_type == 'checkbox':
                    # For checkbox, check if the value is in the list of selections for the step
                    if isinstance(user_selections_for_step, list) and button_value in user_selections_for_step:
                        button_text = f"{CHECKBOX_SELECTED} {button_text}"
                    else:
                        button_text = f"{CHECKBOX_UNSELECTED} {button_text}"
                elif button_type == 'toggle':
                     # For toggle, check the boolean state associated with the value in the selections dict
                     current_state = button_config.get('initialState', False) # Default state if not yet selected
                     if isinstance(user_selections_for_step, dict):
                         current_state = user_selections_for_step.get(button_value, current_state) # Get state from dict, fall back to initial
                     button_text = f"{TOGGLE_ON if current_state else TOGGLE_OFF} {button_text}"
                # 'skip', 'finish' buttons and default buttons don't get state emojis here automatically
                # (though 'finish' in JSON sample has emoji in buttonName)


                # Callback data format: "step_key:row_index:button_index" for option buttons
                # This structure allows identifying the button config later.
                # Adding a prefix like "option:" can make it explicit, but ":" is delimiter.
                # Let's stick to "step_key:row_index:button_index" for clarity.
                callback_data = f"{current_step_key}:{row_index}:{button_index}"

                button_row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            keyboard_rows.append(button_row)


        # Add navigation/completion buttons below the options
        # Add 'Done/Next' button for manual completion steps
        if step_completion_type == 'manual':
            done_button_text = f"{DONE_EMOJI} Done / Next"
            done_callback_data = f"done:{current_step_key}"
            keyboard_rows.append([InlineKeyboardButton(done_button_text, callback_data=done_callback_data)])

        # Add the 'Go Back' button
        back_button_config = step_config.get('backButton')
        if back_button_config:
             # Back button callback data format: "back:current_step_key"
             back_callback_data = f"back:{current_step_key}"
             keyboard_rows.append([InlineKeyboardButton(f"{BACK_EMOJI} Go Back", callback_data=back_callback_data)])


        reply_markup = InlineKeyboardMarkup(keyboard_rows)
        text = step_config.get('description', 'Please make a selection:')

        return reply_markup, text

    def handle_callback_query(self, chat_id, callback_data):
        """
        Processes a callback query from a button click.
        Handles state updates for stateful buttons and determines navigation.

        Args:
            chat_id (int): The user's chat ID.
            callback_data (str): The data received from the button click.

        Returns:
            tuple: (next_step_key_to_render, current_step_key_before_change, processed_value, is_workflow_end)
                   next_step_key_to_render: The key of the step whose menu should be displayed NEXT.
                                            None if the workflow has ended or an error occurred.
                   current_step_key_before_change: The step key the user was on *before* processing the callback.
                                                   Useful for main.py to know which message to edit.
                   processed_value: The value associated with the button click (for data buttons), or None for navigation actions.
                   is_workflow_end: True if the workflow has ended after this click.
        """
        state = self._get_user_state(chat_id)
        current_step_key = state['current_step']
        processed_value = None
        is_workflow_end = False
        next_step_key_to_render = current_step_key # Assume staying on current step by default unless navigation happens

        logger.debug(f"User {chat_id}: Handling callback_data: {callback_data} from step {current_step_key}")

        # --- Handle Navigation/Completion Actions First ---

        # Handle 'back' action
        if callback_data.startswith("back:"):
            # Check if the back button is for the current step
            back_from_step = callback_data.split(':')[1]
            if back_from_step != current_step_key:
                 logger.warning(f"User {chat_id}: 'Back' callback from step '{back_from_step}' received while on step '{current_step_key}'. Ignoring.")
                 # Stay on current step if mismatch
                 return current_step_key, current_step_key, None, False # Return current step, original was current

            previous_step_key = self._get_previous_step_key(current_step_key)
            if previous_step_key:
                self._set_user_step(chat_id, previous_step_key)
                next_step_key_to_render = previous_step_key # We are moving back to the previous step
                logger.info(f"User {chat_id}: Navigated back to step '{previous_step_key}' from '{current_step_key}'.")
            else:
                logger.info(f"User {chat_id}: Cannot go back from initial step '{current_step_key}'. Staying put.")
                # Stay on current step if at the beginning
                next_step_key_to_render = current_step_key # Stay on current step
            # Return the step key to render (either previous or current), the original step key, None value, and not end
            return next_step_key_to_render, current_step_key, None, False


        # Handle 'done' action for manual steps
        if callback_data.startswith("done:"):
            # Ensure the 'done' is for the step the user is actually on
            done_from_step = callback_data.split(':')[1]
            if done_from_step != current_step_key:
                 logger.warning(f"User {chat_id}: 'Done' callback from step '{done_from_step}' received while on step '{current_step_key}'. Ignoring.")
                 return current_step_key, current_step_key, None, False # Stay on current step if mismatch

            # User is done with this manual step, move to the next one
            next_step_key_actual = self._get_next_step_key(current_step_key)
            self._set_user_step(chat_id, next_step_key_actual)
            next_step_key_to_render = next_step_key_actual # Render the next step

            if next_step_key_to_render is None:
                is_workflow_end = True
                logger.info(f"User {chat_id}: Workflow ended after completing step '{current_step_key}'.")

            # Return the step key to render, original step key, None value, and workflow end status
            return next_step_key_to_render, current_step_key, None, is_workflow_end


        # --- Handle Option Button Clicks ---
        # Parse callback data: "step_key:row_index:button_index"
        try:
            parts = callback_data.split(':')
            if len(parts) != 3:
                logger.error(f"Invalid callback data format for option button: {callback_data}")
                return current_step_key, current_step_key, None, False # Stay on current step on error

            clicked_step_key = parts[0]
            row_index = int(parts[1])
            button_index = int(parts[2])

            # Ensure the callback is for the step the user is currently on
            if clicked_step_key != current_step_key:
                logger.warning(f"User {chat_id}: Callback from step '{clicked_step_key}' received while user is on step '{current_step_key}'. Ignoring.")
                return current_step_key, current_step_key, None, False # Stay on current step if mismatch

            step_config = self._get_step_config(current_step_key)
            if not step_config:
                 logger.error(f"Step config not found for key: {current_step_key}")
                 # This case should ideally be caught earlier, but being defensive
                 return None, current_step_key, None, True # Treat as workflow end due to config error

            # Retrieve the button configuration using indices
            row_config = step_config.get('options', [])[row_index]
            button_config = row_config[button_index]

            processed_value = button_config.get('value') # Get the value regardless of type
            button_type = button_config.get('type') # Default is None
            skip_steps = button_config.get('skipSteps', 0) # Default to 0 skip steps

            # --- Update State & Determine Next Step to Render ---

            if button_type == 'finish':
                # This button explicitly ends the workflow
                self._update_selection(chat_id, current_step_key, button_config) # Record value
                is_workflow_end = True
                next_step_key_to_render = None # Signal to main.py that workflow is done
                logger.info(f"User {chat_id}: Workflow explicitly finished from step '{current_step_key}' by button '{button_config.get('buttonName')}'.")

            elif button_type == 'skip':
                 # Record the value and navigate immediately
                 self._update_selection(chat_id, current_step_key, button_config)
                 next_step_key_actual = self._get_next_step_key(current_step_key, skip_steps=skip_steps)
                 self._set_user_step(chat_id, next_step_key_actual)
                 next_step_key_to_render = next_step_key_actual # Render the step after skipping
                 logger.info(f"User {chat_id}: Skipped {skip_steps} steps after clicking '{button_config.get('buttonName')}'. Moving to '{next_step_key_actual}'.")

                 if next_step_key_to_render is None:
                     is_workflow_end = True # Workflow ended due to skip going past the last step
                     logger.info(f"User {chat_id}: Workflow ended after a skip from step '{current_step_key}'.")

            elif button_type in ['radio', 'checkbox', 'toggle']:
                # These buttons change state and stay on the SAME step (usually followed by a 'done' button)
                self._update_selection(chat_id, current_step_key, button_config)
                next_step_key_to_render = current_step_key # Stay on current step to show state change

            else: # Default button (type is None)
                step_completion_type = step_config.get('completionType', 'auto')
                self._update_selection(chat_id, current_step_key, button_config) # Record value

                if step_completion_type == 'auto':
                     # Default button in an 'auto' step navigates immediately
                     next_step_key_actual = self._get_next_step_key(current_step_key)
                     self._set_user_step(chat_id, next_step_key_actual)
                     next_step_key_to_render = next_step_key_actual # Render the next step

                     if next_step_key_to_render is None:
                        is_workflow_end = True # Workflow ended after auto-forward past last step
                        logger.info(f"User {chat_id}: Workflow ended after an auto-forward click from step '{current_step_key}'.")
                else: # Default button in a 'manual' step - stay put (should ideally not exist in manual steps)
                     logger.warning(f"User {chat_id}: Default button '{button_config.get('buttonName')}' clicked in 'manual' step '{current_step_key}'. Staying put.")
                     next_step_key_to_render = current_step_key # Stay on current step

            # Return the step key to render (could be current or next), the original step key,
            # the processed value (only for selection buttons), and workflow end status.
            # Note: For navigation buttons like 'skip', 'done', 'finish', the 'processed_value' return might be less relevant,
            # but we still set it from button_config.get('value').
            return next_step_key_to_render, current_step_key, processed_value, is_workflow_end

        except (IndexError, ValueError) as e:
            logger.error(f"Error processing callback data '{callback_data}' for user {chat_id}: {e}")
            # Stay on current step on error
            return current_step_key, current_step_key, None, False # Return current step, original was current


    def get_user_selections(self, chat_id):
        """Retrieves the final selections made by a user."""
        state = self._get_user_state(chat_id)
        # Optionally filter out keys for steps the user skipped if needed,
        # but returning the raw selections dict is often sufficient.
        # The state might contain entries for skipped steps if a 'skip' button
        # on a previous step set a value like 'any'.
        return state['selections']

    def reset_user_state(self, chat_id):
        """Clears the state for a specific user."""
        if chat_id in self._user_states:
            del self._user_states[chat_id]
            logger.info(f"User {chat_id} state reset.")

    def get_user_current_step_key(self, chat_id):
        """Gets the key of the user's current step."""
        state = self._get_user_state(chat_id)
        return state['current_step']


# Helper function to load workflow data from a JSON file
def load_workflow_data(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            logger.info(f"Successfully loaded workflow data from {filepath}")
            return data
    except FileNotFoundError:
        logger.error(f"Workflow file not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {filepath}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading {filepath}: {e}")
        return None