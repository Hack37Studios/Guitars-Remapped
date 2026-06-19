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

 Build an EXE
 
 1. Install packaging tools:
 ```
 python -m pip install -r dev-requirements.txt
 ```
 2. Build with PyInstaller:
 ```
 build_exe.bat
 ```
 3. Find the executable in the `dist` folder.
 
Notes
- On Windows, controllers should appear as joysticks when connected (USB or Bluetooth).
- If a mapping doesn't trigger, try refreshing joysticks and re-mapping.
 
UI Improvements
- The app uses a cleaner `ttk` look and a larger layout for easier use.
- A live guitar mockup on the right highlights fret buttons and strum actions as you press them on the controller.
- Use the mockup to visually verify which controller inputs are being received while mapping.
