import threading
import json
import queue
import time
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog

try:
    import pygame
except Exception as e:
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

        self.map_queue = queue.Queue()
        self.capture_queue = queue.Queue()
        self.mappings = []
        self.running = False
        self.keyboard = KeyController()

        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

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
                # If someone is capturing a mapping, forward the raw event
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
            # try typing raw string
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
    def __init__(self):
        super().__init__()
        self.title('Guitar-to-Keyboard Mapper')
        self.geometry('700x420')

        self.mapper = ControllerMapper()

        self.create_widgets()
        self.refresh_joysticks()

    def create_widgets(self):
        frame = tk.Frame(self)
        frame.pack(fill='both', expand=True, padx=8, pady=8)

        left = tk.Frame(frame)
        left.pack(side='left', fill='y', padx=(0,8))

        tk.Label(left, text='Detected Joysticks').pack()
        self.jlist = tk.Listbox(left, height=6)
        self.jlist.pack()
        tk.Button(left, text='Refresh', command=self.refresh_joysticks).pack(fill='x')

        mid = tk.Frame(frame)
        mid.pack(side='left', fill='both', expand=True)

        tk.Label(mid, text='Mappings').pack()
        self.map_list = tk.Listbox(mid)
        self.map_list.pack(fill='both', expand=True)

        btnrow = tk.Frame(mid)
        btnrow.pack(fill='x')
        tk.Button(btnrow, text='Add Mapping', command=self.add_mapping).pack(side='left')
        tk.Button(btnrow, text='Remove Selected', command=self.remove_selected).pack(side='left')

        right = tk.Frame(frame)
        right.pack(side='left', fill='y', padx=(8,0))
        tk.Button(right, text='Load...', command=self.load_mappings).pack(fill='x')
        tk.Button(right, text='Save...', command=self.save_mappings).pack(fill='x')
        self.start_btn = tk.Button(right, text='Start Listening', command=self.toggle_start)
        self.start_btn.pack(fill='x')
        tk.Button(right, text='Help', command=self.show_help).pack(fill='x')

    def refresh_joysticks(self):
        self.jlist.delete(0, tk.END)
        names = self.mapper.list_joysticks()
        for n in names:
            self.jlist.insert(tk.END, n)

    def add_mapping(self):
        if not self.mapper.joysticks:
            messagebox.showerror('No joystick', 'No joystick detected. Connect your guitar controller and click Refresh.')
            return

        # Capture controller input
        messagebox.showinfo('Capture', 'After closing this box, press the guitar control you want to map.')

        captured = {}

        def on_capture(event):
            # classify event
            if event.type == pygame.JOYBUTTONDOWN:
                captured.update({'type': 'button', 'joy': event.joy, 'index': event.button})
            elif event.type == pygame.JOYHATMOTION:
                captured.update({'type': 'hat', 'joy': event.joy, 'index': event.hat, 'value': list(event.value)})
            elif event.type == pygame.JOYAXISMOTION:
                # record direction
                dir = 1 if event.value > 0 else -1
                captured.update({'type': 'axis', 'joy': event.joy, 'index': event.axis, 'dir': dir, 'threshold': 0.6})

        # push the callback function into the capture queue
        self.mapper.capture_queue.put(lambda ev_callback: None)  # placeholder to indicate capture mode

        # instead use a simple blocking wait for next event
        done = threading.Event()

        def waiter(ev):
            on_capture(ev)
            done.set()

        # place real callback
        try:
            self.mapper.capture_queue.get_nowait()
        except Exception:
            pass
        self.mapper.capture_queue.put(waiter)

        # wait up to 8 seconds for input
        t0 = time.time()
        while not done.is_set() and time.time() - t0 < 8:
            time.sleep(0.01)

        if not captured:
            messagebox.showwarning('Timeout', 'No controller input detected.')
            try:
                self.mapper.capture_queue.get_nowait()
            except Exception:
                pass
            return

        # Ask for keyboard key
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
            self.start_btn.config(text='Start Listening')
        else:
            self.mapper.start()
            self.start_btn.config(text='Stop Listening')

    def show_help(self):
        help_text = (
            'Usage:\n'
            '- Connect your guitar controller (Santroller RB/BT or Guitar Hero).\n'
            "- Click 'Refresh' to detect joysticks.\n"
            "- Click 'Add Mapping', then press the guitar button to capture it.\n"
            "- Enter the keyboard key name (e.g. space, a, left, enter).\n"
            "- Save/load profiles as JSON.\n"
            "- Click 'Start Listening' to forward controller buttons to keyboard events.\n"
        )
        messagebox.showinfo('Help', help_text)


if __name__ == '__main__':
    app = App()
    app.mainloop()
