import threading
import json
import queue
import time
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
from tkinter import ttk

try:
    import pygame
except Exception:
    raise SystemExit("pygame is required. Install with: pip install pygame")

try:
    from pynput.keyboard import Controller as KeyController, Key
except Exception:
    raise SystemExit("pynput is required. Install with: pip install pynput")


class ControllerMapper:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.joysticks = []
        self._refresh_joysticks()

        self.capture_queue = queue.Queue()
        self.mappings = []
        self.running = False
        self.keyboard = KeyController()
        self._pressed_keys = set()
        self.ui_callback = None

        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def register_ui_callback(self, cb):
        self.ui_callback = cb

    def _refresh_joysticks(self):
        self.joysticks = []
        for i in range(pygame.joystick.get_count()):
            j = pygame.joystick.Joystick(i)
            j.init()
            self.joysticks.append(j)

    def list_joysticks(self):
        self._refresh_joysticks()
        return [j.get_name() for j in self.joysticks]

    def capture_input(self, timeout=12):
        if not self.joysticks:
            return {}

        baseline = []
        pygame.event.pump()
        for joy in self.joysticks:
            baseline.append({
                'buttons': [joy.get_button(i) for i in range(joy.get_numbuttons())],
                'hats': [joy.get_hat(i) for i in range(joy.get_numhats())],
                'axes': [joy.get_axis(i) for i in range(joy.get_numaxes())],
            })

        start = time.time()
        while time.time() - start < timeout:
            pygame.event.pump()
            for joy_id, joy in enumerate(self.joysticks):
                for i in range(joy.get_numbuttons()):
                    value = joy.get_button(i)
                    if value and not baseline[joy_id]['buttons'][i]:
                        return {'type': 'button', 'joy': joy_id, 'index': i}

                for i in range(joy.get_numhats()):
                    value = joy.get_hat(i)
                    if value != baseline[joy_id]['hats'][i]:
                        return {'type': 'hat', 'joy': joy_id, 'index': i, 'value': list(value)}

                for i in range(joy.get_numaxes()):
                    value = joy.get_axis(i)
                    prev = baseline[joy_id]['axes'][i]
                    if abs(value - prev) > 0.25 and abs(value) > 0.2:
                        return {
                            'type': 'axis',
                            'joy': joy_id,
                            'index': i,
                            'dir': 1 if value > prev else -1,
                            'threshold': 0.2
                        }
            time.sleep(0.01)

        return {}

    def _poll_loop(self):
        while True:
            for event in pygame.event.get():
                # send to UI for live feedback
                if self.ui_callback:
                    try:
                        self.ui_callback(event)
                    except Exception:
                        pass

                # forward to any capture callback
                if not self.capture_queue.empty():
                    try:
                        cb = self.capture_queue.get_nowait()
                        if cb:
                            complete = cb(event)
                            if not complete:
                                self.capture_queue.put(cb)
                    except Exception:
                        pass

                # If running, handle mapped events
                if self.running:
                    self._handle_event(event)
            time.sleep(0.006)

    def _handle_event(self, event):
        # Button press/release: hold while down, release on up
        if event.type == pygame.JOYBUTTONDOWN:
            for m in self.mappings:
                if m['type'] == 'button' and m['joy'] == event.joy and m['index'] == event.button:
                    self._press_key(m['key'])
        elif event.type == pygame.JOYBUTTONUP:
            for m in self.mappings:
                if m['type'] == 'button' and m['joy'] == event.joy and m['index'] == event.button:
                    self._release_key(m['key'])

        # Hat motion: press when value matches mapping, release otherwise
        elif event.type == pygame.JOYHATMOTION:
            for m in self.mappings:
                if m['type'] == 'hat' and m['joy'] == event.joy and m['index'] == event.hat:
                    if tuple(m['value']) == tuple(event.value):
                        self._press_key(m['key'])
                    else:
                        self._release_key(m['key'])

        # Axis motion: press while above threshold in the mapped direction, release when not
        elif event.type == pygame.JOYAXISMOTION:
            for m in self.mappings:
                if m['type'] == 'axis' and m['joy'] == event.joy and m['index'] == event.axis:
                    dir = m.get('dir', 1)
                    thresh = m.get('threshold', 0.6)
                    val = event.value
                    if dir > 0:
                        if val > thresh:
                            self._press_key(m['key'])
                        else:
                            self._release_key(m['key'])
                    else:
                        if val < -thresh:
                            self._press_key(m['key'])
                        else:
                            self._release_key(m['key'])

    def _send_key(self, key_name):
        try:
            k = getattr(Key, key_name) if hasattr(Key, key_name) else key_name
            self.keyboard.press(k)
            self.keyboard.release(k)
        except Exception:
            try:
                self.keyboard.press(key_name)
                self.keyboard.release(key_name)
            except Exception:
                print(f"Failed to send key {key_name}")

    def _press_key(self, key_name):
        # Idempotent press: only press if not already pressed
        if key_name in self._pressed_keys:
            return
        try:
            k = getattr(Key, key_name) if hasattr(Key, key_name) else key_name
            self.keyboard.press(k)
            self._pressed_keys.add(key_name)
        except Exception:
            try:
                self.keyboard.press(key_name)
                self._pressed_keys.add(key_name)
            except Exception:
                print(f"Failed to press key {key_name}")

    def _release_key(self, key_name):
        # Idempotent release: only release if currently pressed
        if key_name not in self._pressed_keys:
            return
        try:
            k = getattr(Key, key_name) if hasattr(Key, key_name) else key_name
            self.keyboard.release(k)
            self._pressed_keys.remove(key_name)
        except Exception:
            try:
                self.keyboard.release(key_name)
                self._pressed_keys.remove(key_name)
            except Exception:
                # ensure we don't leak state
                self._pressed_keys.discard(key_name)
                print(f"Failed to release key {key_name}")

    def stop(self):
        self.running = False

    def start(self):
        self.running = True

    def add_mapping(self, mapping):
        self.mappings.append(mapping)

    def remove_mapping(self, idx):
        if 0 <= idx < len(self.mappings):
            del self.mappings[idx]

    def save_mappings(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.mappings, f, indent=2)

    def load_mappings(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            self.mappings = json.load(f)


class App(tk.Tk):
    FRET_COLORS = ['#1abc9c', '#e74c3c', '#f1c40f', '#3498db', '#e67e22']

    def __init__(self):
        super().__init__()
        self.title('Guitar-to-Keyboard Mapper')
        self.geometry('1200x650')
        self.configure(bg='#1a1a1a')

        style = ttk.Style(self)
        # Modern dark theme
        style.theme_use('clam')
        style.configure('TFrame', background='#1a1a1a')
        style.configure('TLabel', background='#1a1a1a', foreground='#ecf0f1', font=('Segoe UI', 10))
        style.configure('TButton', background='#2d2d2d', foreground='#ecf0f1')
        style.map('TButton', background=[('active', '#3a3a3a')])
        style.configure('TLabelframe', background='#1a1a1a', foreground='#ecf0f1')
        style.configure('TLabelframe.Label', background='#1a1a1a', foreground='#ecf0f1')
        style.configure('TSeparator', background='#3a3a3a')

        self.mapper = ControllerMapper()
        self.mapper.register_ui_callback(self._on_controller_event)

        # Diagram button mapping: maps controller button index to diagram element name
        self.diagram_button_map = {
            0: 'fret_0', 1: 'fret_1', 2: 'fret_2', 3: 'fret_3', 4: 'fret_4',
            5: 'strum_up', 6: 'strum_down', 7: 'whammy', 8: 'start', 9: 'back'
        }
        self.diagram_elements = [
            'fret_0', 'fret_1', 'fret_2', 'fret_3', 'fret_4',
            'strum_up', 'strum_down', 'whammy', 'start', 'back'
        ]
        self.diagram_element_var = tk.StringVar(value=self.diagram_elements[0])

        self.create_widgets()
        self.refresh_joysticks()

    def create_widgets(self):
        container = ttk.Frame(self, padding=12)
        container.pack(fill='both', expand=True)

        # LEFT PANEL: controls, joysticks, load/save
        left_panel = ttk.Frame(container)
        left_panel.pack(side='left', fill='both', expand=True, padx=(0, 12))

        ttk.Label(left_panel, text='Detected Joysticks', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 8))
        self.jlist = tk.Listbox(left_panel, height=4, bg='#2d2d2d', fg='#ecf0f1', font=('Segoe UI', 9))
        self.jlist.pack(fill='x')
        ttk.Button(left_panel, text='Refresh Devices', command=self.refresh_joysticks).pack(fill='x', pady=(8, 12))

        ttk.Separator(left_panel, orient='horizontal').pack(fill='x', pady=8)

        ttk.Label(left_panel, text='Mappings', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 8))
        self.map_list = tk.Listbox(left_panel, bg='#2d2d2d', fg='#ecf0f1', font=('Segoe UI', 9), height=16)
        self.map_list.pack(fill='both', expand=True, pady=(0, 8))

        btnrow = ttk.Frame(left_panel)
        btnrow.pack(fill='x', pady=(0, 12))
        ttk.Button(btnrow, text='Add', command=self.add_mapping).pack(side='left', padx=(0, 4))
        ttk.Button(btnrow, text='Remove', command=self.remove_selected).pack(side='left')

        ttk.Separator(left_panel, orient='horizontal').pack(fill='x', pady=8)

        ctrl_row = ttk.Frame(left_panel)
        ctrl_row.pack(fill='x', pady=(0, 4))
        ttk.Button(ctrl_row, text='Load', command=self.load_mappings).pack(side='left', padx=(0, 4))
        ttk.Button(ctrl_row, text='Save', command=self.save_mappings).pack(side='left')

        self.start_btn = ttk.Button(left_panel, text='▶ Start Listening', command=self.toggle_start)
        self.start_btn.pack(fill='x', pady=(0, 4))

        ttk.Label(left_panel, text='Diagram Element', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(6, 4))
        self.diagram_menu = ttk.OptionMenu(left_panel, self.diagram_element_var, self.diagram_elements[0], *self.diagram_elements)
        self.diagram_menu.pack(fill='x')
        ttk.Button(left_panel, text='Remap Selected Element', command=self.configure_diagram).pack(fill='x', pady=(4, 8))

        ttk.Label(left_panel, text='Current Diagram Mapping', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 4))
        self.diagram_status = tk.Listbox(left_panel, bg='#2d2d2d', fg='#ecf0f1', font=('Segoe UI', 9), height=8)
        self.diagram_status.pack(fill='both', expand=False, pady=(0, 4))
        self.refresh_diagram_status()

        ttk.Button(left_panel, text='? Help', command=self.show_help).pack(fill='x')

        # RIGHT PANEL: guitar display (narrow)
        right_panel = ttk.Frame(container)
        right_panel.pack(side='left', fill='y', padx=(12, 0))
        ttk.Label(right_panel, text='Guitar', font=('Segoe UI', 11, 'bold')).pack(anchor='center', pady=(0, 8))
        self.guitar_canvas = tk.Canvas(right_panel, width=180, height=600, bg='#0d0d0d', highlightthickness=1, highlightbackground='#3a3a3a')
        self.guitar_canvas.pack(fill='both', expand=True)

        self._create_guitar_mockup()

    def _create_guitar_mockup(self):
        c = self.guitar_canvas
        c.delete("all")

        x = 90

    # -------------------
    # Headstock (Les Paul style)
    # -------------------
        c.create_polygon(
            x-18, 10,
            x-25, 40,
            x+25, 40,
            x+18, 10,
            fill="#111111",
            outline="#cccccc",
            width=2
        )

        # tuning pegs
        for i in range(3):
            yy = 15 + i * 10

            c.create_oval(
                x-32, yy,
                x-24, yy + 8,
                fill="silver",
                outline=""
            )

            c.create_oval(
                x+24, yy,
                x+32, yy + 8,
                fill="silver",
                outline=""
            )

        # -------------------
        # Neck
        # -------------------
        c.create_rectangle(
            x-12, 40,
            x+12, 350,
            fill="#5c3b20",
            outline="#c89b63",
            width=2
        )

        # fret markers
        for y in range(70, 340, 35):
            c.create_line(
                x-12, y,
                x+12, y,
                fill="#d9d9d9"
            )

        # strings
        for sx in [x-8, x-4, x, x+4, x+8]:
            c.create_line(
                sx, 40,
                sx, 350,
                fill="#d4af37"
            )

        # -------------------
        # Colored frets
        # -------------------
        self.fret_items = []

        fret_colors = [
            "#2ecc71",  # green
            "#e74c3c",  # red
            "#f1c40f",  # yellow
            "#3498db",  # blue
            "#e67e22"   # orange
        ]

        for i, color in enumerate(fret_colors):
            yy = 90 + i * 45

            item = c.create_oval(
                x-14,
                yy-14,
                x+14,
                yy+14,
                fill=color,
                outline="#111111",
                width=2
            )

            self.fret_items.append((f"fret_{i}", item))

        # -------------------
        # Les Paul body
        # -------------------
        body = c.create_polygon(
            x-55, 350,
            x-80, 390,
            x-75, 470,
            x-50, 520,
            x-10, 545,

            x+10, 545,
            x+50, 520,
            x+75, 470,
            x+80, 390,
            x+55, 350,

            fill="#111111",
            outline="#dddddd",
            width=3,
            smooth=True
        )

        # cream pickguard
        c.create_polygon(
            x+5, 385,
            x+45, 410,
            x+30, 470,
            x, 455,
            fill="#f7f1d5",
            outline="#cccccc"
        )

        # pickups
        c.create_rectangle(
            x-20, 390,
            x+20, 410,
            fill="silver",
            outline="#444"
        )

        c.create_rectangle(
            x-20, 435,
            x+20, 455,
            fill="silver",
            outline="#444"
        )

        # bridge
        c.create_rectangle(
            x-25,
            475,
            x+25,
            482,
            fill="silver",
            outline=""
        )

        # -------------------
        # Strum bar
        # -------------------
        self.strum_up = c.create_rectangle(
            x-45, 395,
            x-20, 430,
            fill="#7f8c8d",
            outline="#2d2d2d",
            width=2
        )

        self.fret_items.append(("strum_up", self.strum_up))

        c.create_text(
            x-32,
            412,
            text="▲",
            fill="white",
            font=("Segoe UI", 10, "bold")
        )

        self.strum_down = c.create_rectangle(
            x-45, 435,
            x-20, 470,
            fill="#7f8c8d",
            outline="#2d2d2d",
            width=2
        )

        self.fret_items.append(("strum_down", self.strum_down))

        c.create_text(
            x-32,
            452,
            text="▼",
            fill="white",
            font=("Segoe UI", 10, "bold")
        )

        # -------------------
        # Whammy Bar
        # -------------------
        self.whammy = c.create_line(
            x+45, 420,
            x+70, 500,
            fill="silver",
            width=4
        )

        self.fret_items.append(("whammy", self.whammy))

        # -------------------
        # Start / Back
        # -------------------
        self.start_btn_item = c.create_oval(
            x+20, 365,
            x+32, 377,
            fill="#27ae60"
        )

        self.fret_items.append(("start", self.start_btn_item))

        self.back_btn_item = c.create_oval(
            x+38, 365,
            x+50, 377,
            fill="#c0392b"
        )

        self.fret_items.append(("back", self.back_btn_item))

    def _on_controller_event(self, event):
        # schedule UI update on main thread
        try:
            self.after(0, lambda ev=event: self._handle_ui_event(ev))
        except Exception:
            pass

    def _handle_ui_event(self, event):
        c = self.guitar_canvas
        # button presses
        element_name = None
        if event.type == pygame.JOYBUTTONDOWN:
            btn_idx = getattr(event, 'button', None)
            if btn_idx is not None:
                element_name = self.diagram_button_map.get(btn_idx)
        elif event.type == pygame.JOYHATMOTION:
            key = f"hat_{event.hat}_{event.value[0]}_{event.value[1]}"
            element_name = self.diagram_button_map.get(key)
            val = tuple(getattr(event, 'value', (0, 0)))
            if val == (0, 1):
                c.itemconfig(self.strum_up, fill='#ecf0f1')
                self.after(140, lambda: c.itemconfig(self.strum_up, fill='#7f8c8d'))
            elif val == (0, -1):
                c.itemconfig(self.strum_down, fill='#ecf0f1')
                self.after(140, lambda: c.itemconfig(self.strum_down, fill='#7f8c8d'))
        elif event.type == pygame.JOYAXISMOTION:
            key = None
            if abs(event.value) > 0.7:
                key = f"axis_{event.axis}_{1 if event.value > 0 else -1}"
            if key is not None:
                element_name = self.diagram_button_map.get(key)
            val = getattr(event, 'value', 0)
            if abs(val) > 0.7:
                if val < 0:
                    c.itemconfig(self.strum_up, fill='#ecf0f1')
                    self.after(140, lambda: c.itemconfig(self.strum_up, fill='#7f8c8d'))
                else:
                    c.itemconfig(self.strum_down, fill='#ecf0f1')
                    self.after(140, lambda: c.itemconfig(self.strum_down, fill='#7f8c8d'))

        if element_name:
            for name, item_id in self.fret_items:
                if name == element_name:
                    if name.startswith('fret_'):
                        fret_num = int(name.split('_')[1])
                        c.itemconfig(item_id, fill=self.FRET_COLORS[fret_num % len(self.FRET_COLORS)])
                        self.after(180, lambda i=item_id, fn=fret_num: c.itemconfig(i, fill=self.FRET_COLORS[fn % len(self.FRET_COLORS)]))
                    else:
                        c.itemconfig(item_id, fill='#ecf0f1')
                        self.after(140, lambda i=item_id: c.itemconfig(i, fill='#95a5a6'))
                    break
        elif event.type == pygame.JOYAXISMOTION:
            # treat axis motion as strum if axis value large
            val = getattr(event, 'value', 0)
            if abs(val) > 0.7:
                if val < 0:
                    c.itemconfig(self.strum_up, fill='#ecf0f1')
                    self.after(140, lambda: c.itemconfig(self.strum_up, fill='#7f8c8d'))
                else:
                    c.itemconfig(self.strum_down, fill='#ecf0f1')
                    self.after(140, lambda: c.itemconfig(self.strum_down, fill='#7f8c8d'))

    def refresh_joysticks(self):
        self.jlist.delete(0, tk.END)
        names = self.mapper.list_joysticks()
        for n in names:
            self.jlist.insert(tk.END, n)

    def _start_capture_dialog(self, title, description, callback, timeout=8):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry('360x120')
        dialog.resizable(False, False)
        dialog.configure(bg='#1a1a1a')
        dialog.grab_set()

        ttk.Label(dialog, text=description, wraplength=340, justify='center', font=('Segoe UI', 10), background='#1a1a1a', foreground='#ecf0f1').pack(fill='both', expand=True, padx=12, pady=(12, 8))
        status_label = ttk.Label(dialog, text='Listening for controller input...', font=('Segoe UI', 9), background='#1a1a1a', foreground='#95a5a6')
        status_label.pack(fill='x', padx=12)

        def finish(captured):
            if dialog.winfo_exists():
                dialog.destroy()
            self.after(0, lambda: callback(captured))

        def capture_worker():
            captured = self.mapper.capture_input(timeout=timeout)
            finish(captured)

        threading.Thread(target=capture_worker, daemon=True).start()

    def _finish_add_mapping(self, captured):
        if not captured:
            messagebox.showwarning('Timeout', 'No controller input detected. Try pressing the control again.')
            return

        key = simpledialog.askstring('Keyboard Key', 'Enter the keyboard key or special key name (e.g. space, enter, left):')
        if not key:
            messagebox.showinfo('Cancelled', 'Mapping cancelled.')
            return

        mapping = captured
        mapping['key'] = key
        self.mapper.add_mapping(mapping)
        self.refresh_map_list()

    def add_mapping(self):
        if not self.mapper.joysticks:
            messagebox.showerror('No joystick', 'No joystick detected. Connect your guitar controller and click Refresh.')
            return

        self._start_capture_dialog(
            'Capture Button',
            'Press the guitar control you want to map now. The app will capture the first input detected.',
            self._finish_add_mapping
        )

    def refresh_map_list(self):
        self.map_list.delete(0, tk.END)
        for m in self.mapper.mappings:
            desc = f"{m['type']} (joy{m['joy']} idx{m['index']}) -> {m['key']}"
            if m['type'] == 'axis':
                desc = f"axis{m['index']} dir {m.get('dir',1)} -> {m['key']}"
            if m['type'] == 'hat':
                desc = f"hat{m['index']} value {m.get('value')} -> {m['key']}"
            self.map_list.insert(tk.END, desc)

    def refresh_diagram_status(self):
        self.diagram_status.delete(0, tk.END)
        element_to_buttons = {}
        for btn, element in self.diagram_button_map.items():
            element_to_buttons.setdefault(element, []).append(str(btn))

        for element in self.diagram_elements:
            buttons = element_to_buttons.get(element, ['--'])
            self.diagram_status.insert(tk.END, f"{element}: {', '.join(buttons)}")

    def remove_selected(self):
        sel = self.map_list.curselection()
        if not sel:
            return
        idx = sel[0]
        self.mapper.remove_mapping(idx)
        self.refresh_map_list()

    def save_mappings(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON files','*.json')])
        if not path:
            return
        self.mapper.save_mappings(path)
        messagebox.showinfo('Saved', f'Mappings saved to {path}')

    def load_mappings(self):
        path = filedialog.askopenfilename(filetypes=[('JSON files','*.json')])
        if not path:
            return
        self.mapper.load_mappings(path)
        self.refresh_map_list()

    def toggle_start(self):
        if self.mapper.running:
            self.mapper.stop()
            self.start_btn.config(text='▶ Start Listening')
        else:
            self.mapper.start()
            self.start_btn.config(text='⏸ Stop Listening')

    def configure_diagram(self):
        # Allow user to remap buttons to diagram elements
        if not self.mapper.joysticks:
            messagebox.showerror('No joystick', 'No joystick detected. Connect your guitar controller and click Refresh Devices.')
            return

        element = self.diagram_element_var.get()
        self._start_capture_dialog(
            'Capture Diagram Button',
            f'Press the controller input you want to assign to: {element} now.',
            lambda captured: self._finish_configure_diagram(captured, element)
        )

    def _finish_configure_diagram(self, captured, element):
        if not captured:
            messagebox.showwarning('Timeout', 'No controller input detected in time. Try pressing the control again.')
            return

        if captured['type'] == 'hat':
            captured_btn = f"hat_{captured['index']}_{captured['value'][0]}_{captured['value'][1]}"
        elif captured['type'] == 'axis':
            captured_btn = f"axis_{captured['index']}_{captured['dir']}"
        else:
            captured_btn = captured['index']

        self.diagram_button_map[captured_btn] = element
        self.refresh_diagram_status()
        messagebox.showinfo('Mapped', f'{element} mapped to {captured_btn}')

    def show_help(self):
        help_text = (
            'Usage:\n'
            '- Connect your guitar controller (Santroller RB/BT or Guitar Hero).\n'
            "- Click 'Refresh Devices' to detect joysticks.\n"
            "- Click 'Configure Diagram' to map controller buttons to guitar diagram elements.\n"
            "- Click 'Add' to create keyboard mappings.\n"
            "- Press the controller button, then enter the keyboard key (e.g. space, a, left).\n"
            "- Save/load profiles as JSON.\n"
            "- Click 'Start Listening' to forward controller buttons to keyboard events.\n"
        )
        messagebox.showinfo('Help', help_text)


if __name__ == '__main__':
    app = App()
    app.mainloop()
