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
                            cb(event)
                    except Exception:
                        pass

                # If running, handle mapped events
                if self.running:
                    self._handle_event(event)
            time.sleep(0.006)

    def _handle_event(self, event):
        if event.type == pygame.JOYBUTTONDOWN:
            for m in self.mappings:
                if m['type'] == 'button' and m['joy'] == event.joy and m['index'] == event.button:
                    self._send_key(m['key'])
        elif event.type == pygame.JOYHATMOTION:
            for m in self.mappings:
                if m['type'] == 'hat' and m['joy'] == event.joy and m['index'] == event.hat and tuple(m['value']) == tuple(event.value):
                    self._send_key(m['key'])
        elif event.type == pygame.JOYAXISMOTION:
            for m in self.mappings:
                if m['type'] == 'axis' and m['joy'] == event.joy and m['index'] == event.axis:
                    dir = m.get('dir', 1)
                    thresh = m.get('threshold', 0.6)
                    val = event.value
                    if dir > 0 and val > thresh:
                        self._send_key(m['key'])
                    if dir < 0 and val < -thresh:
                        self._send_key(m['key'])

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
        self.configuring_diagram = False

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
        ttk.Button(left_panel, text='Configure Diagram', command=self.configure_diagram).pack(fill='x', pady=(0, 4))
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
        if self.configuring_diagram:
            # During configuration, just capture the button and show it
            if event.type == pygame.JOYBUTTONDOWN:
                btn_idx = getattr(event, 'button', None)
                if btn_idx is not None:
                    messagebox.showinfo('Button Captured', f'Button {btn_idx} captured for diagram.')
            return
            
        c = self.guitar_canvas
        # button presses
        if event.type == pygame.JOYBUTTONDOWN:
            btn_idx = getattr(event, 'button', None)
            if btn_idx is not None and btn_idx in self.diagram_button_map:
                element_name = self.diagram_button_map[btn_idx]
                # Find and highlight the element
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
        elif event.type == pygame.JOYHATMOTION:
            # show strum up/down when hat moves
            val = tuple(getattr(event, 'value', (0,0)))
            if val == (0, 1):
                c.itemconfig(self.strum_up, fill='#ecf0f1')
                self.after(140, lambda: c.itemconfig(self.strum_up, fill='#7f8c8d'))
            if val == (0, -1):
                c.itemconfig(self.strum_down, fill='#ecf0f1')
                self.after(140, lambda: c.itemconfig(self.strum_down, fill='#7f8c8d'))
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

    def add_mapping(self):
        if not self.mapper.joysticks:
            messagebox.showerror('No joystick', 'No joystick detected. Connect your guitar controller and click Refresh.')
            return

        messagebox.showinfo('Capture', 'After closing this box, press the guitar control you want to map.')

        captured = {}

        def on_capture(event):
            if event.type == pygame.JOYBUTTONDOWN:
                captured.update({'type': 'button', 'joy': event.joy, 'index': event.button})
            elif event.type == pygame.JOYHATMOTION:
                captured.update({'type': 'hat', 'joy': event.joy, 'index': event.hat, 'value': list(event.value)})
            elif event.type == pygame.JOYAXISMOTION:
                dir = 1 if event.value > 0 else -1
                captured.update({'type': 'axis', 'joy': event.joy, 'index': event.axis, 'dir': dir, 'threshold': 0.6})

        # place callback and wait for event
        done = threading.Event()

        def waiter(ev):
            on_capture(ev)
            done.set()

        try:
            # flush any existing
            while True:
                self.mapper.capture_queue.get_nowait()
        except Exception:
            pass
        self.mapper.capture_queue.put(waiter)

        t0 = time.time()
        while not done.is_set() and time.time() - t0 < 8:
            time.sleep(0.01)

        try:
            self.mapper.capture_queue.get_nowait()
        except Exception:
            pass

        if not captured:
            messagebox.showwarning('Timeout', 'No controller input detected.')
            return

        key = simpledialog.askstring('Keyboard Key', 'Enter the keyboard key or special key name (e.g. space, enter, left):')
        if not key:
            messagebox.showinfo('Cancelled', 'Mapping cancelled.')
            return

        mapping = captured
        mapping['key'] = key
        self.mapper.add_mapping(mapping)
        self.refresh_map_list()

    def refresh_map_list(self):
        self.map_list.delete(0, tk.END)
        for m in self.mapper.mappings:
            desc = f"{m['type']} (joy{m['joy']} idx{m['index']}) -> {m['key']}"
            if m['type'] == 'axis':
                desc = f"axis{m['index']} dir {m.get('dir',1)} -> {m['key']}"
            if m['type'] == 'hat':
                desc = f"hat{m['index']} value {m.get('value')} -> {m['key']}"
            self.map_list.insert(tk.END, desc)

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
        
        # List available diagram elements
        diagram_elements = [
            'fret_0', 'fret_1', 'fret_2', 'fret_3', 'fret_4',
            'strum_up', 'strum_down', 'whammy', 'start', 'back'
        ]
        
        # Create a simple dialog to select which element to configure
        element = simpledialog.askstring(
            'Configure Diagram',
            'Which element to map?\n(fret_0-4, strum_up, strum_down, whammy, start, back)\n\nEnter element name:'
        )
        
        if not element or element not in diagram_elements:
            messagebox.showwarning('Invalid', 'Invalid element name.')
            return
        
        messagebox.showinfo('Capture Button', f'Press the button on your controller for: {element}')
        
        captured_btn = None
        done = threading.Event()
        
        def on_capture(event):
            nonlocal captured_btn
            if event.type == pygame.JOYBUTTONDOWN:
                captured_btn = getattr(event, 'button', None)
                done.set()
        
        try:
            while True:
                self.mapper.capture_queue.get_nowait()
        except Exception:
            pass
        
        self.mapper.capture_queue.put(on_capture)
        
        t0 = time.time()
        while not done.is_set() and time.time() - t0 < 8:
            time.sleep(0.01)
        
        try:
            self.mapper.capture_queue.get_nowait()
        except Exception:
            pass
        
        if captured_btn is None:
            messagebox.showwarning('Timeout', 'No button pressed in time.')
            return
        
        # Map the button to the element
        self.diagram_button_map[captured_btn] = element
        messagebox.showinfo('Mapped', f'Button {captured_btn} -> {element}')

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
