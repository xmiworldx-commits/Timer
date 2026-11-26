"""Stopwatch + countdown timer app (Tkinter).

Run: python stopwatch_timer.py  (or build an exe with PyInstaller)
Two tabs: Stopwatch (with laps) and Timer (countdown with alert).
"""

import threading
import time
import tkinter as tk
import winsound

DARK_BG = "#1e1e2e"
DISPLAY_BG = "#11111b"
TEXT_FG = "#cdd6f4"
ACCENT_FG = "#11111b"
BUTTON_BG = "#313244"
BUTTON_ACTIVE = "#45475a"
GREEN = "#a6e3a1"
RED = "#f38ba8"
BLUE = "#89b4fa"
PURPLE = "#cba6f7"
YELLOW = "#f9e2af"
FONT_DISPLAY = ("Consolas", 40)
FONT_MED = ("Segoe UI", 14)
FONT_SMALL = ("Segoe UI", 11)

TICK_MS = 30  # display refresh; stopwatch shows centiseconds


def fmt_elapsed(seconds: float) -> str:
    """1h 23m 45.67s style display for the stopwatch."""
    total_cs = round(seconds * 100)
    hours, rem = divmod(total_cs, 3600 * 100)
    minutes, rem = divmod(rem, 60 * 100)
    secs, cs = divmod(rem, 100)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"
    return f"{minutes:02d}:{secs:02d}.{cs:02d}"


def fmt_remaining(seconds: float) -> str:
    """Ceiling countdown: 2.5s left shows as 0:03 while it is running."""
    total = int(-(-seconds // 1))  # ceil for positive floats
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def make_button(parent, text, bg, command=None, width=8):
    button = tk.Button(
        parent, text=text, font=FONT_MED, bg=bg, fg=ACCENT_FG,
        activebackground=BUTTON_ACTIVE, activeforeground=ACCENT_FG,
        relief="flat", width=width, pady=6, command=command,
    )
    return button


class TimerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Stopwatch & Timer")
        self.resizable(False, False)
        self.configure(bg=DARK_BG, padx=10, pady=10)
        self.stopwatch = StopwatchFrame(self)
        self.timer_frame = TimerFrame(self)
        self.stopwatch.pack(fill="x", expand=True)
        self.timer_frame.pack(fill="x", expand=True)
        self.stopwatch.start_ui()
        self.timer_frame.start_ui()
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"{width}x{height}")
        self.minsize(width, height)
        self.maxsize(width, height)


class StopwatchFrame(tk.Frame):
    """Counts up from zero. Supports laps and pause/resume."""

    def __init__(self, master) -> None:
        super().__init__(master, bg=DARK_BG)
        self.elapsed = 0.0        # frozen time while paused
        self.started = None       # monotonic time when (re)started
        self.after_id = None
        self.lap_marks = []       # total elapsed at each lap

        self.time_label = tk.Label(
            self, text="00:00.00", font=FONT_DISPLAY, bg=DISPLAY_BG,
            fg=TEXT_FG, padx=24, pady=18,
        )

    def start_ui(self) -> None:
        # let both columns share extra width so buttons fill the frame
        self.columnconfigure(0, weight=1, uniform="sw")
        self.columnconfigure(1, weight=1, uniform="sw")
        self.time_label.grid(row=0, column=0, columnspan=2, sticky="we",
                             pady=(0, 10))
        self.start_button = make_button(self, "Start", GREEN, self.start_stop)
        self.start_button.grid(row=1, column=0, sticky="we", padx=4)
        self.reset_button = make_button(self, "Reset", RED, self.reset)
        self.reset_button.grid(row=1, column=1, sticky="we", padx=4)
        self.lap_button = make_button(self, "Lap", PURPLE, self.lap)
        self.lap_button.grid(row=2, column=0, columnspan=2, sticky="we",
                             padx=4, pady=(6, 0))
        self.laps = tk.Listbox(self, height=5, bg=DISPLAY_BG, fg=TEXT_FG,
                               font=FONT_SMALL, relief="flat",
                               highlightthickness=0)
        self.laps.grid(row=3, column=0, columnspan=2, sticky="we",
                       padx=4, pady=(10, 4))

    # -- state transitions --

    def is_running(self) -> bool:
        return self.started is not None

    def total_now(self) -> float:
        if self.is_running():
            return self.elapsed + (time.monotonic() - self.started)
        return self.elapsed

    def start_stop(self) -> None:
        if self.is_running():                     # pause
            self.elapsed = self.total_now()
            self.started = None
            self.start_button.configure(text="Resume", bg=YELLOW)
        else:                                     # (re)start
            self.started = time.monotonic()
            self.start_button.configure(text="Pause", bg=BLUE)
            self._tick()

    def reset(self) -> None:
        if self.started is not None:
            self.started = time.monotonic()
        self.elapsed = 0.0
        self.lap_marks.clear()
        self.laps.delete(0, "end")
        self._refresh()

    def lap(self) -> None:
        total = self.total_now()
        previous = self.lap_marks[-1] if self.lap_marks else 0.0
        self.lap_marks.append(total)
        self.laps.insert(0, f"Lap {len(self.lap_marks):>2}   "
                            f"+{fmt_elapsed(total - previous)}   "
                            f"(total {fmt_elapsed(total)})")

    # -- display --

    def _tick(self) -> None:
        if not self.is_running():
            return
        self._refresh()
        self.after_id = self.after(TICK_MS, self._tick)

    def _refresh(self) -> None:
        self.time_label.configure(text=fmt_elapsed(self.total_now()))


class TimerFrame(tk.Frame):
    """Countdown. Set hours/minutes/seconds, start, get a beep at zero."""

    def __init__(self, master) -> None:
        super().__init__(master, bg=DARK_BG)
        self.remaining = 0.0
        self.deadline = None
        self.after_id = None
        self.blink_id = None
        self.blink_state = False
        self.alert_stop = None      # threading.Event — стоп сигнала таймера
        self.alert_thread = None

        self.time_label = tk.Label(
            self, text="00:00", font=FONT_DISPLAY, bg=DISPLAY_BG,
            fg=TEXT_FG, padx=24, pady=18,
        )

    def start_ui(self) -> None:
        # let the three columns share extra width so buttons fill the frame
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.time_label.grid(row=0, column=0, columnspan=3, sticky="we",
                             pady=(0, 10))
        row = tk.Frame(self, bg=DARK_BG)
        row.grid(row=1, column=0, columnspan=3, pady=(0, 10))
        self.entries = []
        for label_text in ("Hours", "Minutes", "Seconds"):
            cell = tk.Frame(row, bg=DARK_BG)
            cell.pack(side="left", padx=6)
            entry = tk.Entry(cell, width=4, font=FONT_MED, justify="center",
                             bg=DISPLAY_BG, fg=TEXT_FG, insertbackground=TEXT_FG,
                             relief="flat", highlightthickness=1,
                             highlightbackground=BUTTON_BG)
            entry.pack()
            tk.Label(cell, text=label_text, font=FONT_SMALL, bg=DARK_BG,
                     fg=TEXT_FG).pack()
            entry.bind("<KeyRelease>", lambda e: self._reflect())
            self.entries.append(entry)

        self.start_button = make_button(self, "Start", GREEN, self.start_stop)
        self.start_button.grid(row=2, column=0, columnspan=3, sticky="we",
                               padx=4)
        self.reset_button = make_button(self, "Reset", RED, self.reset)
        self.reset_button.grid(row=3, column=0, columnspan=3, sticky="we",
                               padx=4, pady=(6, 0))

    # -- state transitions --

    def is_running(self) -> bool:
        return self.deadline is not None

    def _set_duration(self, seconds: float) -> None:
        self.remaining = max(0.0, seconds)
        self._refresh()

    def set_from_entries(self) -> bool:
        try:
            hours = int(self.entries[0].get() or "0")
            minutes = int(self.entries[1].get() or "0")
            seconds = int(self.entries[2].get() or "0")
            if min(hours, minutes, seconds) < 0:
                raise ValueError
        except ValueError:
            self._show_error("Invalid duration")
            return False
        self._set_duration(hours * 3600 + minutes * 60 + seconds)
        return True

    def start_stop(self) -> None:
        if self.is_running():                      # pause
            self.remaining = max(0.0, self.deadline - time.monotonic())
            self.deadline = None
            self.start_button.configure(text="Resume", bg=YELLOW)
            return
        if self.remaining <= 0:                    # fresh start from entries
            if not self.set_from_entries():
                return
        if self.remaining <= 0:
            self._show_error("Set a duration first")
            return
        self._stop_alert()          # пользователь среагировал на сигнал
        self.deadline = time.monotonic() + self.remaining
        self.start_button.configure(text="Pause", bg=BLUE)
        self._blink_cancel()
        self._tick()

    def reset(self) -> None:
        self._stop_alert()          # пользователь среагировал на сигнал
        self.deadline = None
        self._blink_cancel()
        self.start_button.configure(text="Start", bg=GREEN)
        self.set_from_entries()

    # -- countdown --

    def _tick(self) -> None:
        if not self.is_running():
            return
        self.remaining = max(0.0, self.deadline - time.monotonic())
        if self.remaining <= 0:
            self._expired()
            return
        self._refresh()
        self.after_id = self.after(TICK_MS, self._tick)

    def _expired(self) -> None:
        self.deadline = None
        self.remaining = 0.0
        self._refresh()
        self.start_button.configure(text="Start", bg=GREEN)
        self._start_alert()
        self.blink_state = True
        self._blink()

    def _start_alert(self) -> None:
        """Звуковой сигнал при конце отсчёта. winsound.Beep играет всегда —
        он не зависит от системной схемы звуков Windows (в отличие от
        MessageBeep). Повторяется двухтональный звонок, пока пользователь
        не нажмёт Start или Reset."""
        self._stop_alert()
        stop = threading.Event()
        self.alert_stop = stop

        def ring() -> None:
            # Синтезированный бип: не зависит от схемы звуков и системных файлов.
            while not stop.is_set():
                for freq in (880, 1175):
                    if stop.is_set():
                        return
                    try:
                        winsound.Beep(freq, 350)
                    except Exception:
                        return

        self.alert_thread = threading.Thread(target=ring, daemon=True)
        self.alert_thread.start()

    def _stop_alert(self) -> None:
        if self.alert_stop is not None:
            self.alert_stop.set()
            self.alert_stop = None
        self.alert_thread = None

    def _blink(self) -> None:
        self.blink_state = not self.blink_state
        self.time_label.configure(fg=RED if self.blink_state else TEXT_FG)
        self.blink_id = self.after(500, self._blink)

    def _blink_cancel(self) -> None:
        if self.blink_id is not None:
            self.after_cancel(self.blink_id)
            self.blink_id = None
        self.time_label.configure(fg=TEXT_FG)

    # -- input rules --

    def _reflect(self) -> None:
        """Echo the typed duration into the big display while paused."""
        if not self.is_running():
            self.set_from_entries()

    def _show_error(self, message: str) -> None:
        self.time_label.configure(text=message, fg=RED)

    def _refresh(self) -> None:
        text = fmt_remaining(self.remaining)
        if self.remaining < 10 and self.is_running():
            self.time_label.configure(text=text, fg=RED)
        else:
            self.time_label.configure(text=text, fg=TEXT_FG)


if __name__ == "__main__":
    TimerApp().mainloop()
