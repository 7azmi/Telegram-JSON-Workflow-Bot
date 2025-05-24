# Telegram JSON Workflow Bot

Build dynamic, multi-step inline button workflows for your Telegram bot using simple JSON configuration.

This project provides a Python module (`module.py`) that reads a workflow definition from a JSON file and handles the logic for navigating through steps, managing user selections (radio, checkbox, toggle), and updating the inline keyboard interface in Telegram. A demo bot using `python-telegram-bot` is included (`main.py`).

## Quick Demo
![Peek 2025-05-25 06-59](https://github.com/user-attachments/assets/940022cb-9dc7-4e92-b3d9-c7980e8840ce)


## ✨ Features

*   **JSON Configuration:** Define your entire workflow structure, steps, buttons, and logic in a single JSON file.
*   **Multi-Step Navigation:** Supports seamless transitions between steps, including automatic forwarding, explicit "Done" buttons for manual steps, "Go Back" navigation, and configurable "Skip" buttons.
*   **Diverse Button Types:**
    *   **Default:** Forward to the next step automatically upon click.
    *   **Radio:** Select one option from a group per step (pre-selection and validation included for manual steps).
    *   **Checkbox:** Select multiple options from a step.
    *   **Toggle:** Flip a single on/off setting.
    *   **Finish:** Explicitly end the workflow and display selections.
*   **Flexible Layout:** Define button placement using arrays of arrays in the JSON.
*   **User State Management:** Tracks each user's progress and selections using `context.user_data`.
*   **MarkdownV2 Support:** Automatically escapes text to prevent parsing issues.

## 🚀 Installation

1.  Clone or download the project files (`module.py`, `main.py`, `workflow_config.json`).
2.  Install the `python-telegram-bot` library:
    ```bash
    pip install python-telegram-bot --upgrade
    ```

## 🛠️ Setup

1.  Get a Telegram Bot Token from the @BotFather on Telegram.
2.  Open `main.py` and replace `"YOUR_BOT_TOKEN"` with your actual token.
3.  Customize the `workflow_config.json` file to define your desired workflow (see JSON Structure below).
4.  Run the bot:
    ```bash
    python main.py
    ```

## 🚦 Usage

1.  Start a chat with your bot on Telegram.
2.  Send the `/start` command to begin the workflow.
3.  Interact with the inline buttons. The bot will update the message with the next step's options based on your configuration.
4.  Use `/selections` at any point to see the raw selections collected so far (useful for debugging).
5.  The workflow ends when you reach a step with a "Finish" button or if a skip action goes past the last defined step.

## 📂 File Structure

```
.
├── main.py                # Demo bot implementation using the module
├── module.py              # The core WorkflowManager module
└── workflow_config.json   # Example workflow definition in JSON
```

## ⚙️ JSON Configuration

The `workflow_config.json` file defines the structure and behavior of your bot's inline button workflow.

The root of the JSON is an object containing one key, which is the name of your workflow (e.g., `"sample_workflow"`). This key maps to an object containing step definitions.

```json
{
  "your_workflow_name": {
    "step_key_1": { ... },
    "step_key_2": { ... },
    ...
  }
}
```

Each **Step Object** (identified by its `step_key`) defines a single screen or menu the user sees:

```json
{
  "your_step_key": {
    "description": "Text displayed above buttons.",
    "completionType": "auto" | "manual", // Optional: How to proceed (default is auto)
    "options": [
      // Array of arrays defining button rows
      [ { ... }, { ... } ], // Row 1
      [ { ... } ]            // Row 2
    ],
    "backButton": {          // Optional: Configuration for the "Go Back" button
      "buttonName": "⬅️ Go Back"
    }
  }
}
```

*   `description`: (String) Text displayed to the user. Automatically escaped for MarkdownV2.
*   `completionType`: (String, Optional)
    *   `"auto"` (default): Clicking any non-stateful button (type `null` or `skip`) in this step automatically moves to the next step.
    *   `"manual"`: Clicking stateful buttons (`radio`, `checkbox`, `toggle`) updates the selection but keeps the user on the same step. A "✅ Done / Next" button will appear, which the user must click to proceed to the next step. Radio button groups in manual steps require one selection each to proceed.
*   `options`: (Array of Arrays) Defines the inline buttons. Each inner array is a row.
*   `backButton`: (Object, Optional) If present, a "Go Back" button with the specified `buttonName` will appear below the options if there is a previous step in the workflow sequence.

Each **Button Object** within the `options` arrays defines a single inline button:

```json
{
  "buttonName": "Button Text", // Text displayed on the button
  "value": "button_value",     // Value associated with this selection/action
  "type": "radio" | "checkbox" | "toggle" | "skip" | "finish", // Optional: Button behavior
  "radioGroup": "group_name",  // Required for type="radio"
  "skipSteps": 1,              // Required for type="skip": number of steps to skip
  "initialState": false        // Optional for type="toggle": default state
}
```

*   `buttonName`: (String) The text on the button.
*   `value`: (String or Boolean for toggle) The value recorded in the user's selections when this button is pressed. For `toggle` buttons, this is the key under which the boolean state is stored.
*   `type`: (String, Optional) Defines button behavior.
    *   `(omitted or null)`: Default forwarding button. Records `value` and moves to the next step if `completionType` is `"auto"`.
    *   `"radio"`: Part of a mutually exclusive group (`radioGroup`). Records `value` for the specified group. Requires manual completion (`completionType: "manual"`) to proceed.
    *   `"checkbox"`: Toggles selection on/off. Records/removes `value` from a list. Requires manual completion (`completionType: "manual"`) to proceed.
    *   `"toggle"`: Flips a boolean state associated with `value`. Records state as `{value: boolean}`. Requires manual completion (`completionType: "manual"`) to proceed.
    *   `"skip"`: Records `value` and skips `skipSteps` number of *subsequent* steps.
    *   `"finish"`: Records `value` and immediately ends the workflow, displaying the final selections summary.
*   `radioGroup`: (String) **Required for `type="radio"`**. Groups radio buttons for mutual exclusion within the step.
*   `skipSteps`: (Integer) **Required for `type="skip"`**. The number of steps in the sequence to skip after the current one.
*   `initialState`: (Boolean, Optional) **Optional for `type="toggle"`**. The default state when the button is first displayed. Defaults to `false`.

## 📋 Example `workflow_config.json`

(See the provided `workflow_config.json` file for a complete example demonstrating all features).

## 💖 Contributing

Feel free to submit issues or pull requests on the GitHub repository.

## 📄 License

you see it it's yours

## Credits

*   Built with the goat [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot).
