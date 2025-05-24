# module.py - Streamlined Interface

import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging
from collections import defaultdict
from telegram.helpers import escape_markdown # Import escaping utility

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


class InlineWorkflowManager:
    """
    Manages a multi-step inline button workflow defined by a JSON structure file.
    Provides a simple interface for starting, processing clicks, and getting UI responses.
    Handles stateful buttons (radio, checkbox, toggle) and navigation (forward, back, skip, manual completion, finish).
    Stores user state in context.user_data under a workflow-specific key.
    Implements radio button group validation and pre-selection for manual steps.
    Handles MarkdownV2 escaping for dynamic text.
    """
    # Key under which workflow state is stored in context.user_data
    STATE_KEY = "_workflow_state"

    def __init__(self, workflow_filepath):
        """
         Initializes the WorkflowManager by loading workflow data from a JSON file.

        Args:
            workflow_filepath (str): The path to the workflow JSON file.
        """
        self.workflow_filepath = workflow_filepath
        workflow_data = self._load_workflow_data(workflow_filepath)
        if not workflow_data:
             logger.error("Failed to load workflow data during initialization.")
             # In a real app, you might raise an exception here or have a fallback workflow
             self.workflow_name = None
             self.workflow_steps = {}
             self._step_keys = []
             self._radio_groups_per_step = {} # Ensure this is initialized even on failure
             self.is_initialized = False
             return

        if len(workflow_data) != 1:
             logger.warning("Workflow data contains multiple top-level keys. Using the first one found.")

        self.workflow_name = list(workflow_data.keys())[0]
        self.workflow_steps = workflow_data[self.workflow_name]
        self._step_keys = list(self.workflow_steps.keys()) # Ordered list of step keys (Python 3.7+ guarantees order)

        # Pre-calculate radio groups per step for faster validation/pre-selection
        self._radio_groups_per_step = {}
        for step_key, step_config in self.workflow_steps.items():
            radio_groups = set()
            for row in step_config.get('options', []):
                for button_config in row:
                    if button_config.get('type') == 'radio' and 'radioGroup' in button_config:
                        radio_groups.add(button_config['radioGroup'])
            if radio_groups:
                self._radio_groups_per_step[step_key] = list(radio_groups) # Store as list

        self.is_initialized = True
        logger.info(f"WorkflowManager initialized for workflow: '{self.workflow_name}' from '{workflow_filepath}' with steps: {self._step_keys}")


    def _load_workflow_data(self, filepath):
        """Loads workflow data from a JSON file."""
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

    # --- Internal State & Navigation Helpers ---

    def _get_step_config(self, step_key):
        """Retrieves the configuration for a given step key."""
        return self.workflow_steps.get(step_key)

    def _get_initial_step_key(self):
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

    # --- User State Management in context.user_data ---

    def _get_workflow_state_from_context(self, context):
        """Gets or initializes the workflow state from context.user_data."""
        # Check if initialized before accessing workflow_name
        if not self.is_initialized:
             logger.error("WorkflowManager not initialized successfully. Cannot get state from context.")
             # Return a dummy structure to prevent immediate KeyError, but indicate issue
             return {'current_step': None, 'selections': {}}

        if self.workflow_name not in context.user_data:
             context.user_data[self.workflow_name] = {
                 'current_step': self._get_initial_step_key(), # Use internal method
                 'selections': {}
             }
             logger.debug(f"Initialized workflow state in context.user_data['{self.workflow_name}']")

        # Ensure 'selections' is a dict within the workflow state
        workflow_state = context.user_data[self.workflow_name]
        if 'selections' not in workflow_state or not isinstance(workflow_state['selections'], dict):
             logger.warning(f"User data for workflow '{self.workflow_name}' corrupted. Resetting selections.")
             workflow_state['selections'] = {}

        return workflow_state


    def _get_user_current_step_key(self, context):
        """Gets the key of the user's current step from context."""
        workflow_state = self._get_workflow_state_from_context(context)
        return workflow_state.get('current_step')

    def _set_user_step(self, context, step_key):
        """Sets the user's current step in context."""
        workflow_state = self._get_workflow_state_from_context(context)
        workflow_state['current_step'] = step_key
        logger.debug(f"User current step set to: {step_key}")

    def _get_selection_value(self, context, step_key):
        """Retrieves the recorded selection(s) for a specific step from context."""
        workflow_state = self._get_workflow_state_from_context(context)
        return workflow_state['selections'].get(step_key)

    def _update_selection(self, context, step_key, button_config):
        """Updates the user's selection for a step in context based on button type."""
        workflow_state = self._get_workflow_state_from_context(context)
        selection_value = button_config.get('value')
        button_type = button_config.get('type')
        radio_group = button_config.get('radioGroup')

        # Only update state for buttons that represent a selection
        if button_type in [None, 'radio', 'checkbox', 'toggle', 'skip']: # Include skip as it has a value like 'any'
             current_selection_state = workflow_state['selections'].get(step_key)

             if button_type is None or button_type == 'skip':
                  workflow_state['selections'][step_key] = selection_value
                  logger.debug(f"User: Selection button '{button_config.get('buttonName')}' ({button_type}) pressed. Value '{selection_value}' recorded for step '{step_key}'.")

             elif button_type == 'radio':
                  if not isinstance(current_selection_state, dict):
                       current_selection_state = {}
                       logger.debug(f"User: Initializing/resetting radio selection state for step '{step_key}'.")

                  if radio_group:
                      current_selection_state[radio_group] = selection_value
                      workflow_state['selections'][step_key] = current_selection_state
                      logger.debug(f"User: Radio button '{button_config.get('buttonName')}' pressed. Group '{radio_group}' value '{selection_value}' recorded for step '{step_key}'.")
                  else:
                      logger.warning(f"User: Radio button '{button_config.get('buttonName')}' missing 'radioGroup'. Value '{selection_value}' ignored for state update.")

             elif button_type == 'checkbox':
                 if not isinstance(current_selection_state, list):
                      current_selection_state = []
                      logger.warning(f"User: State for step '{step_key}' was not a list for checkbox. Resetting.")

                 if selection_value in current_selection_state:
                     current_selection_state.remove(selection_value)
                     logger.debug(f"User: Checkbox '{button_config.get('buttonName')}' deselected. Value '{selection_value}' removed from step '{step_key}'.")
                 else:
                     current_selection_state.append(selection_value)
                     logger.debug(f"User: Checkbox '{button_config.get('buttonName')}' selected. Value '{selection_value}' added to step '{step_key}'.")

                 workflow_state['selections'][step_key] = current_selection_state

             elif button_type == 'toggle':
                 if not isinstance(current_selection_state, dict):
                      current_selection_state = {}

                 current_state_for_value = current_selection_state.get(selection_value, button_config.get('initialState', False))
                 current_selection_state[selection_value] = not current_state_for_value
                 logger.debug(f"User: Toggle '{button_config.get('buttonName')}' flipped to {current_selection_state[selection_value]}.")
                 workflow_state['selections'][step_key] = current_selection_state

    def _validate_manual_step_completion(self, context, step_key):
        """
        Validates if the required selections have been made for a manual completion step.
        Checks if at least one option is selected in each radio group for this step.
        Returns True if validation passes, False otherwise.
        """
        step_config = self._get_step_config(step_key)
        if step_config.get('completionType') != 'manual':
             return True # Validation only applies to manual steps

        required_radio_groups = self._radio_groups_per_step.get(step_key, [])

        # If no radio groups, consider valid *for radios*. Add other validation if needed.
        if not required_radio_groups:
             return True

        user_selections = self._get_selection_value(context, step_key)

        # For radio groups, the selection state for the step should be a dictionary {group: value}
        if not isinstance(user_selections, dict):
             logger.debug(f"Step '{step_key}' requires radio selections but state is not a dict ({type(user_selections).__name__}).")
             return False # Must be a dictionary to hold radio group selections state

        # Check if a non-None selection exists for every required radio group
        for group in required_radio_groups:
             if group not in user_selections or user_selections.get(group) is None:
                  logger.debug(f"Step '{step_key}' missing selection for radio group '{group}'. State: {user_selections}")
                  return False # Missing a selection for a required group

        logger.debug(f"Step '{step_key}' manual completion validation passed.")
        return True


    # --- Public Interface Methods ---

    def start_workflow(self, context):
        """
        Initializes user state and generates the UI for the first step.

        Args:
            context (ContextTypes.DEFAULT_TYPE): The context object.

        Returns:
            tuple: (InlineKeyboardMarkup, str) or (None, str) if an error occurred.
        """
        if not self.is_initialized:
             return None, escape_markdown("Workflow manager failed to initialize. Please contact support.", version=2)

        self.reset_user_state(context)
        # generate_keyboard_and_text will get the initial step key from the newly reset state
        return self._generate_keyboard_and_text(context) # Use internal method


    def process_callback_and_get_response(self, context, callback_data):
        """
        Processes a button callback, updates user state, and prepares the response
        (next step's UI or final summary/error).

        Args:
            context (ContextTypes.DEFAULT_TYPE): The context object.
            callback_data (str): The data received from the button click.

        Returns:
            tuple: (response_text, reply_markup, is_final_message)
                   response_text: The text to display in the message (already MarkdownV2 escaped).
                   reply_markup: The InlineKeyboardMarkup to display (or None).
                   is_final_message: True if this response is the final message of the workflow.
        """
        if not self.is_initialized:
             return escape_markdown("Workflow manager not initialized. Cannot process click.", version=2), None, True # Treat as end state error

        current_step_key = self._get_user_current_step_key(context)

        # --- Handle Critical Error: Missing current step key ---
        if not current_step_key:
             logger.error(f"User state missing current_step_key in context.user_data['{self.workflow_name}'] for callback {callback_data}. Resetting state.")
             self.reset_user_state(context)
             # Return end state with escaped error message
             return escape_markdown("Your workflow state was lost. Please start again with /start.", version=2), None, True


        logger.debug(f"User: Processing callback_data: {callback_data} from step {current_step_key}")

        message_override_text = None # Text to show instead of step description (e.g., validation error)
        is_workflow_end = False
        next_step_key_after_logic = current_step_key # Default to staying on the same step after logic


        # --- Handle Navigation/Completion Actions First (Back, Done) ---

        # Handle 'back' action
        if callback_data.startswith("back:"):
            back_from_step = callback_data.split(':')[1]
            if back_from_step != current_step_key:
                 logger.warning(f"User: 'Back' callback from step '{back_from_step}' received while on step '{current_step_key}'. Ignoring.")
                 # Stay on current step if mismatch, but generate UI for current step
                 return self._generate_keyboard_and_text(context) + (False,) # Append is_final_message=False

            previous_step_key = self._get_previous_step_key(current_step_key)
            if previous_step_key:
                self._set_user_step(context, previous_step_key)
                next_step_key_after_logic = previous_step_key # We are moving back to the previous step
                logger.info(f"User: Navigated back to step '{previous_step_key}' from '{current_step_key}'.")
            else:
                logger.info(f"User: Cannot go back from initial step '{current_step_key}'. Staying put.")
                next_step_key_after_logic = current_step_key # Stay on current step
            # The UI for the step determined by next_step_key_after_logic will be generated below

        # Handle 'done' action for manual steps
        elif callback_data.startswith("done:"):
            done_from_step = callback_data.split(':')[1]
            if done_from_step != current_step_key:
                 logger.warning(f"User: 'Done' callback from step '{done_from_step}' received while on step '{current_step_key}'. Ignoring.")
                 # Stay on current step if mismatch
                 return self._generate_keyboard_and_text(context) + (False,) # Append is_final_message=False

            # Validate completion requirements for this manual step
            if self._validate_manual_step_completion(context, current_step_key):
                 # Validation passed, move to the next step
                 next_step_key_actual = self._get_next_step_key(current_step_key)
                 self._set_user_step(context, next_step_key_actual)
                 next_step_key_after_logic = next_step_key_actual # Render the next step

                 if next_step_key_after_logic is None:
                     is_workflow_end = True
                     logger.info(f"User: Workflow ended after completing step '{current_step_key}'.")

            else:
                 # Validation failed, stay on the current step and show an error message
                 logger.info(f"User: Manual step '{current_step_key}' completion validation failed.")
                 next_step_key_after_logic = current_step_key # Stay on the current step
                 # Escape the error message for MarkdownV2 - done in _validate_manual_step_completion
                 message_override_text = escape_markdown("⚠️ Please make all required selections before proceeding.", version=2)


        # --- Handle Option Button Clicks ---
        # Parse callback data: "step_key:row_index:button_index"
        else: # It's a regular option button click
            try:
                parts = callback_data.split(':')
                if len(parts) != 3:
                    logger.error(f"Invalid callback data format for option button: {callback_data}")
                    # Return error message and stay on current step
                    return escape_markdown("An internal error occurred (invalid button data).", version=2), self._generate_keyboard_and_text(context)[0], False

                clicked_step_key = parts[0]
                row_index = int(parts[1])
                button_index = int(parts[2])

                # Ensure the callback is for the step the user is currently on
                if clicked_step_key != current_step_key:
                    logger.warning(f"User: Callback from step '{clicked_step_key}' received while user is on step '{current_step_key}'. Ignoring.")
                    # Stay on current step if mismatch
                    return self._generate_keyboard_and_text(context) + (False,) # Append is_final_message=False


                step_config = self._get_step_config(current_step_key)
                if not step_config:
                     logger.error(f"Step config not found for key: {current_step_key}")
                     self.reset_user_state(context) # Reset on critical config error
                     # Return end state with error message
                     return escape_markdown("An internal error occurred (step configuration missing). Please restart.", version=2), None, True

                # Retrieve the button configuration using indices
                row_config = step_config.get('options', [])[row_index]
                button_config = row_config[button_index]

                button_type = button_config.get('type') # Default is None
                skip_steps = button_config.get('skipSteps', 0) # Default to 0 skip steps
                step_completion_type = step_config.get('completionType', 'auto') # Default to auto


                # --- Update State & Determine Next Step ---

                if button_type == 'finish':
                    # This button explicitly ends the workflow
                    self._update_selection(context, current_step_key, button_config) # Record value if any
                    is_workflow_end = True
                    next_step_key_after_logic = None # Signal workflow end

                elif button_type == 'skip':
                     # Record the value and navigate immediately
                     self._update_selection(context, current_step_key, button_config)
                     next_step_key_actual = self._get_next_step_key(current_step_key, skip_steps=skip_steps)
                     self._set_user_step(context, next_step_key_actual)
                     next_step_key_after_logic = next_step_key_actual # Render the step after skipping

                     if next_step_key_after_logic is None:
                         is_workflow_end = True # Workflow ended due to skip going past the last step
                         logger.info(f"User: Workflow ended after a skip from step '{current_step_key}'.")

                elif button_type in ['radio', 'checkbox', 'toggle']:
                    # These buttons change state and typically stay on the SAME step
                    # (navigation happens via 'done' button in manual steps)
                    self._update_selection(context, current_step_key, button_config)
                    next_step_key_after_logic = current_step_key # Stay on current step to show state change

                else: # Default button (type is None)
                    # Record value and navigate immediately if completionType is 'auto'
                    self._update_selection(context, current_step_key, button_config)

                    if step_completion_type == 'auto':
                         next_step_key_actual = self._get_next_step_key(current_step_key)
                         self._set_user_step(context, next_step_key_actual)
                         next_step_key_after_logic = next_step_key_actual # Render the next step

                         if next_step_key_after_logic is None:
                            is_workflow_end = True # Workflow ended after auto-forward past last step
                            logger.info(f"User: Workflow ended after an auto-forward click from step '{current_step_key}'.")
                    else: # Default button in a 'manual' step - stay put (should ideally not exist or be ignored)
                         logger.warning(f"User: Default button '{button_config.get('buttonName')}' clicked in 'manual' step '{current_step_key}'. Staying put.")
                         next_step_key_after_logic = current_step_key # Stay on current step

            except (IndexError, ValueError) as e:
                logger.error(f"Error processing callback data '{callback_data}' for user: {e}", exc_info=True)
                # Stay on current step on error and return an escaped error message
                return escape_markdown("An internal error occurred while processing your request.", version=2), self._generate_keyboard_and_text(context)[0], False # Pass current keyboard

        # --- Prepare Response UI based on Next Step / Workflow End ---

        if is_workflow_end:
            # Workflow finished. Get final selections and prepare summary text.
            final_selections = self.get_user_selections(context)
            # Escape the introductory text, JSON dump should be fine in ```json block
            summary_intro_text = escape_markdown("Workflow completed! Here are your selections:", version=2)
            selections_json_str = json.dumps(final_selections, indent=2)
            response_text = f"{summary_intro_text}\n```json\n{selections_json_str}\n```"
            reply_markup = None # No keyboard needed for the final message

            # Optionally reset state after showing summary
            # self.reset_user_state(context)

        else:
            # Workflow is ongoing. Generate UI for the step determined by next_step_key_after_logic.
            # Ensure the current step in context is set correctly before generating UI
            # (This should have been done above, but double check or rely on _get_workflow_state_from_context's current_step)
            # self._set_user_step(context, next_step_key_after_logic) # This might already be done

            reply_markup, default_step_text = self._generate_keyboard_and_text(context) # text is already escaped description

            # Use override text (like validation error) if it exists, otherwise use the default step text
            response_text = message_override_text if message_override_text is not None else default_step_text

            if not reply_markup and not response_text:
                logger.error(f"generate_keyboard_and_text returned no UI for step '{next_step_key_after_logic}'. State: {self._get_workflow_state_from_context(context)}")
                response_text = escape_markdown("An error occurred generating the next step's UI.", version=2)
                reply_markup = None # Ensure no partial keyboard
                # Consider if this should set is_workflow_end = True


        # Return the prepared response text, reply markup, and workflow end status
        return response_text, reply_markup, is_workflow_end


    def _generate_keyboard_and_text(self, context):
        """
        Generates the InlineKeyboardMarkup and message text for the user's *current* step
        (as stored in context.user_data). Includes emojis for stateful buttons and
        navigation/completion buttons. Applies MarkdownV2 escaping to description text.
        This is an internal helper method.

        Args:
            context (ContextTypes.DEFAULT_TYPE): The context object.

        Returns:
            tuple: (InlineKeyboardMarkup, str) or (None, str) if the step is not found or error.
                   The string is the escaped description.
        """
        current_step_key = self._get_user_current_step_key(context)
        step_config = self._get_step_config(current_step_key)

        if not step_config:
            logger.error(f"Could not find configuration for current step in context: {current_step_key}.")
            # Escape the error message
            return None, escape_markdown("An internal error occurred (step config missing for current step).", version=2)

        keyboard_rows = []
        user_selections_for_step = self._get_selection_value(context, current_step_key)
        step_completion_type = step_config.get('completionType', 'auto') # Default to auto

        # --- Radio Button Pre-selection (for manual steps with radios) ---
        # This ensures a radio button is visually selected and a default value is saved
        # if the user lands on a manual radio step and hasn't selected anything yet.
        required_radio_groups = self._radio_groups_per_step.get(current_step_key, [])
        if step_completion_type == 'manual' and required_radio_groups:
            # Ensure selection state for this step is a dictionary for radio groups
            if not isinstance(user_selections_for_step, dict):
                user_selections_for_step = {}
                # Update state in context immediately
                workflow_state = self._get_workflow_state_from_context(context)
                workflow_state['selections'][current_step_key] = user_selections_for_step
                logger.debug(f"User: Initializing selection state as dict for step '{current_step_key}' for radio pre-selection.")


            initial_selection_made = False
            temp_selections_update = user_selections_for_step.copy() # Work on a copy for pre-selection logic

            for row in step_config.get('options', []):
                 for button_config in row:
                      # Only consider actual radio buttons for pre-selection
                      if button_config.get('type') == 'radio' and 'radioGroup' in button_config:
                           group = button_config['radioGroup']
                           button_value = button_config.get('value')
                           # If this specific group doesn't have a selection yet
                           if group not in temp_selections_update or temp_selections_update.get(group) is None:
                                # Select this button's value as the default for this group
                                temp_selections_update[group] = button_value
                                initial_selection_made = True # Flag that we modified state
                                logger.debug(f"Pre-selecting radio option '{button_config.get('buttonName')}' for group '{group}' in step '{current_step_key}'.")


            # If we made any initial selections during this generation, save the modified selections dict back to context
            if initial_selection_made:
                 workflow_state = self._get_workflow_state_from_context(context)
                 workflow_state['selections'][current_step_key] = temp_selections_update
                 # Update the local variable used for generating emojis with the latest state
                 user_selections_for_step = temp_selections_update
                 logger.debug(f"User: Saved pre-selected radio options for step '{current_step_key}'. Final state: {user_selections_for_step}")


        # --- Build Option Buttons ---
        for row_index, row in enumerate(step_config.get('options', [])):
            button_row = []
            for button_index, button_config in enumerate(row):
                button_text = button_config['buttonName']
                button_value = button_config.get('value')
                button_type = button_config.get('type') # Default is None

                # Modify button text with emoji based on state and type
                if button_type == 'radio':
                    # For radio, check if the user's selection dictionary for this step has this group/value combination
                    selected = False
                    # Check if state is a dict and contains the group
                    if isinstance(user_selections_for_step, dict) and 'radioGroup' in button_config:
                         group = button_config['radioGroup']
                         # Check if the value associated with the group in state matches this button's value
                         if user_selections_for_step.get(group) == button_value:
                             selected = True
                    button_text = f"{RADIO_SELECTED} {button_text}" if selected else f"{RADIO_UNSELECTED} {button_text}"

                elif button_type == 'checkbox':
                    # For checkbox, check if the value is in the list of selections for the step
                    selected = False
                    # Check if state is a list
                    if isinstance(user_selections_for_step, list) and button_value in user_selections_for_step:
                        selected = True
                    button_text = f"{CHECKBOX_SELECTED} {button_text}" if selected else f"{CHECKBOX_UNSELECTED} {button_text}"

                elif button_type == 'toggle':
                     # For toggle, check the boolean state associated with the value in the selections dict
                     current_state = button_config.get('initialState', False) # Default state if not yet selected in state
                     # Check if state is a dict
                     if isinstance(user_selections_for_step, dict):
                         # Get state from dict, fall back to button's initial state if not found in state
                         current_state = user_selections_for_step.get(button_value, current_state)
                     button_text = f"{TOGGLE_ON if current_state else TOGGLE_OFF} {button_text}"
                # 'skip', 'finish' buttons and default buttons don't get state emojis here automatically
                # (though 'finish' in JSON sample has emoji in buttonName)


                # Callback data format: "step_key:row_index:button_index" for option buttons
                callback_data = f"{current_step_key}:{row_index}:{button_index}"

                button_row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            keyboard_rows.append(button_row)


        # --- Add Navigation/Completion Buttons ---

        # Add 'Done/Next' button for manual completion steps
        if step_completion_type == 'manual':
            done_button_text = f"{DONE_EMOJI} Done / Next"
            done_callback_data = f"done:{current_step_key}"
            keyboard_rows.append([InlineKeyboardButton(done_button_text, callback_data=done_callback_data)])

        # Add the 'Go Back' button IF configured for this step and a previous step exists
        back_button_config = step_config.get('backButton')
        if back_button_config:
             if self._get_previous_step_key(current_step_key):
                # Back button callback data format: "back:current_step_key"
                back_callback_data = f"back:{current_step_key}"
                keyboard_rows.append([InlineKeyboardButton(f"{BACK_EMOJI} Go Back", callback_data=back_callback_data)])
             else:
                 logger.debug(f"Step '{current_step_key}' has backButton config but is the first step. Not adding back button.")


        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        # Escape the step description for MarkdownV2
        description_text = step_config.get('description', 'Please make a selection:')
        escaped_description = escape_markdown(description_text, version=2)

        return reply_markup, escaped_description


    def get_user_selections(self, context):
        """Retrieves the final selections made by a user from context."""
        workflow_state = self._get_workflow_state_from_context(context)
        # Return a copy to prevent external modification of internal state
        return workflow_state['selections'].copy()

    def reset_user_state(self, context):
        """Clears the state for a specific user in context."""
        # Ensure we only delete our specific workflow state key and check initialization
        if self.is_initialized and self.workflow_name in context.user_data:
            del context.user_data[self.workflow_name]
            logger.info(f"User workflow state '{self.workflow_name}' in context.user_data reset.")
        elif not self.is_initialized:
             logger.warning("Attempted to reset state but WorkflowManager not initialized.")