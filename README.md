# Guitar-to-Keyboard Mapper

Simple Python GUI to map guitar controller inputs (Santroller, Rock Band, Guitar Hero) to keyboard keys.

Requirements
- Python 3.8+
- Install dependencies:

```
python -m pip install -r requirements.txt
```

Run

```
python main.py
```

How it works
- Detects controllers via `pygame.joystick`.
- Use "Add Mapping" to capture a controller input, then enter the keyboard key to map to.
- Save/load mapping profiles as JSON.
- Click "Start Listening" to forward controller events as keyboard presses.

Notes
- On Windows, controllers should appear as joysticks when connected (USB or Bluetooth).
- If a mapping doesn't trigger, try refreshing joysticks and re-mapping.
