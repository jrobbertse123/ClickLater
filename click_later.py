"""
ClickLater - a small self-contained Windows desktop utility (modern UI).

    1. Keep screen active   -> stops the display sleeping / the machine idling.
    2. Click a point        -> click a screen point you pick with a crosshair.
    3. Timed click          -> click that point after an HH:MM:SS countdown.

UI  : CustomTkinter (dark, rounded, gold-on-charcoal).
Core: Win32 via ctypes, all isolated in WinInput - swap-friendly if you ever
      want an AutoHotkey backend.

Run:  python click_later.py

Senior-dev notes inline as  # SENIOR: ...
"""

import os
import sys
import ctypes
from ctypes import wintypes
import tkinter as tk
import customtkinter as ctk


# ---------------------------------------------------------------------------
# SENIOR: DPI awareness before any window exists. CustomTkinter already opts the
# process into per-monitor DPI awareness, but we assert it explicitly so the
# crosshair overlay (a raw tk.Toplevel, NOT a CTk widget) and SetCursorPos()
# both speak the same physical-pixel language on 125/150/175% displays. If we
# skipped this, the point you pick and the point we click would drift apart -
# the #1 scaling bug in any Windows automation tool.
# ---------------------------------------------------------------------------
def _enable_dpi_awareness():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_V2
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()


# ---- palette (matches the reticle icon) -----------------------------------
BG        = "#100d09"
CARD      = "#1c1811"
CARD2     = "#241f16"
EDGE      = "#372d1c"
ACCENT    = "#f5c842"
ACCENT_HI = "#ffdd6e"
ON_ACCENT = "#141109"   # text on top of gold
TEXT      = "#f2ecdf"
MUTED     = "#9a907a"
GHOST_HV  = "#2a2417"
FONT      = "Segoe UI"
MONO      = "Consolas"

APP_NAME  = "ClickLater"
ICON_FILE = "click_later.ico"


# ---------------------------------------------------------------------------
# All OS-level input. Keeping it in ONE class keeps the UI code pure CTk.
# ---------------------------------------------------------------------------
class WinInput:
    ES_CONTINUOUS        = 0x80000000
    ES_SYSTEM_REQUIRED   = 0x00000001
    ES_DISPLAY_REQUIRED  = 0x00000002
    MOUSEEVENTF_MOVE     = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP   = 0x0004

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

    def keep_awake(self, on: bool):
        # SENIOR: ES_CONTINUOUS = hold the state until released; OR-ing
        # SYSTEM/DISPLAY_REQUIRED blocks sleep + screen-blank. ES_CONTINUOUS
        # alone releases it.
        flags = (self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED | self.ES_DISPLAY_REQUIRED
                 if on else self.ES_CONTINUOUS)
        self._kernel32.SetThreadExecutionState(ctypes.c_uint(flags))

    def click(self, x: int, y: int):
        # SENIOR: SetCursorPos takes PHYSICAL pixels; because we're DPI-aware,
        # the coords captured from the overlay line up 1:1.
        self._user32.SetCursorPos(int(x), int(y))
        self._user32.mouse_event(self.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self._user32.mouse_event(self.MOUSEEVENTF_LEFTUP,   0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Fullscreen crosshair overlay (raw tk so CTk scaling can't distort geometry).
# ---------------------------------------------------------------------------
class CrosshairPicker(tk.Toplevel):
    def __init__(self, master, on_pick, on_cancel):
        super().__init__(master)
        self._on_pick, self._on_cancel = on_pick, on_cancel

        u = ctypes.windll.user32
        vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)   # virtual screen origin
        vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)   # virtual screen size

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.30)
        self.configure(cursor="none", bg="#0b0906")
        self.geometry(f"{vw}x{vh}+{vx}+{vy}")

        self.cv = tk.Canvas(self, highlightthickness=0, bg="#0b0906")
        self.cv.pack(fill="both", expand=True)
        self.h = self.cv.create_line(0, 0, 0, 0, fill=ACCENT, width=1)
        self.v = self.cv.create_line(0, 0, 0, 0, fill=ACCENT, width=1)
        self.chip = self.cv.create_rectangle(0, 0, 0, 0, fill="#161206", outline=ACCENT)
        self.txt = self.cv.create_text(0, 0, fill=ACCENT, font=(MONO, 12), anchor="w")
        self.cv.create_text(vw // 2, 30, fill=ACCENT, font=(FONT, 13),
                            text="click to lock a point      Esc to cancel")

        self.bind("<Motion>", self._move)
        self.bind("<Button-1>", self._pick)
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.focus_force()

    def _move(self, e):
        w, h = self.winfo_width(), self.winfo_height()
        self.cv.coords(self.h, 0, e.y, w, e.y)
        self.cv.coords(self.v, e.x, 0, e.x, h)
        # SENIOR: x_root/y_root are TRUE screen pixels = what SetCursorPos wants.
        label = f" {e.x_root}, {e.y_root} "
        self.cv.itemconfig(self.txt, text=label)
        self.cv.coords(self.txt, e.x + 16, e.y + 20)
        bb = self.cv.bbox(self.txt)
        if bb:
            self.cv.coords(self.chip, bb[0] - 4, bb[1] - 3, bb[2] + 4, bb[3] + 3)
            self.cv.tag_raise(self.txt)

    def _pick(self, e):
        x, y = e.x_root, e.y_root
        self.destroy()
        self._on_pick(x, y)

    def _cancel(self):
        self.destroy()
        self._on_cancel()


# ---------------------------------------------------------------------------
# One HH / MM / SS stepper tile.
# ---------------------------------------------------------------------------
class Stepper(ctk.CTkFrame):
    def __init__(self, master, label, maxv, start=0):
        super().__init__(master, fg_color=CARD2, corner_radius=12)
        self.maxv = maxv
        self.value = start
        self._disp = tk.StringVar(value=f"{start:02d}")

        ctk.CTkButton(self, text="▲", width=54, height=22, corner_radius=8,
                      fg_color="transparent", hover_color=GHOST_HV,
                      text_color=ACCENT, font=(FONT, 13),
                      command=lambda: self._step(+1)).grid(row=0, column=0, padx=6, pady=(6, 0))
        ctk.CTkLabel(self, textvariable=self._disp, font=(MONO, 30, "bold"),
                     text_color=TEXT, width=54).grid(row=1, column=0, padx=6)
        ctk.CTkButton(self, text="▼", width=54, height=22, corner_radius=8,
                      fg_color="transparent", hover_color=GHOST_HV,
                      text_color=ACCENT, font=(FONT, 13),
                      command=lambda: self._step(-1)).grid(row=2, column=0, padx=6, pady=(0, 6))
        ctk.CTkLabel(self, text=label, font=(FONT, 10), text_color=MUTED).grid(row=3, column=0, pady=(0, 6))

    def _step(self, d):
        # SENIOR: wrap-around feels nicer than clamping on a time wheel.
        self.value = (self.value + d) % (self.maxv + 1)
        self._disp.set(f"{self.value:02d}")


# ---------------------------------------------------------------------------
# Main window.
# ---------------------------------------------------------------------------
class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.win = WinInput()
        self._point = None
        self._job = None
        self._remaining = 0

        self.title(APP_NAME)
        self.resizable(False, False)
        self._set_icon()

        self._build()
        self._fit()   # SENIOR: size window to content -> never clips at any DPI
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- window chrome -----------------------------------------------------
    def _set_icon(self):
        # SENIOR: in a --onefile build the bundled .ico is unpacked to a temp
        # dir exposed as sys._MEIPASS; fall back to the script dir when running
        # from source. CTk needs the icon set a beat after init, hence after().
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(base, ICON_FILE)
        if os.path.exists(ico):
            self.after(250, lambda: self._safe_icon(ico))

    def _safe_icon(self, ico):
        try:
            self.iconbitmap(ico)
        except Exception:
            pass

    def _fit(self):
        # SENIOR: hardcoding a height gets clipped at 125/150% scaling - exactly
        # the bug we just hit. Instead we measure the content's *requested* size
        # and size the window to it. Crucially we call the BASE Tk geometry, not
        # CTk's override: winfo_reqwidth/height already report real device pixels,
        # whereas CTk.geometry() would re-apply window scaling and double-count.
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        tk.Tk.geometry(self, f"{w}x{h}+{x}+{y}")

    # -- helpers -----------------------------------------------------------
    def _card(self, title):
        f = ctk.CTkFrame(self, fg_color=CARD, corner_radius=16, border_width=1, border_color=EDGE)
        ctk.CTkLabel(f, text=title, font=(FONT, 12, "bold"), text_color=ACCENT).grid(
            row=0, column=0, columnspan=6, sticky="w", padx=16, pady=(12, 2))
        return f

    def _primary(self, parent, text, cmd):
        return ctk.CTkButton(parent, text=text, command=cmd, height=38, corner_radius=10,
                             fg_color=ACCENT, hover_color=ACCENT_HI, text_color=ON_ACCENT,
                             font=(FONT, 13, "bold"))

    def _ghost(self, parent, text, cmd):
        return ctk.CTkButton(parent, text=text, command=cmd, height=38, corner_radius=10,
                             fg_color="transparent", hover_color=GHOST_HV,
                             border_width=1, border_color=EDGE, text_color=TEXT,
                             font=(FONT, 13))

    # -- layout ------------------------------------------------------------
    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 6))
        ctk.CTkLabel(head, text=APP_NAME, font=(FONT, 22, "bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text="click here … later",
                     font=(FONT, 11), text_color=MUTED).grid(row=1, column=0, sticky="w")

        # 1 - keep awake
        c1 = self._card("KEEP SCREEN ACTIVE")
        c1.grid(row=1, column=0, sticky="ew", padx=14, pady=6)
        c1.grid_columnconfigure(0, weight=1)
        self.awake = ctk.CTkSwitch(c1, text="  Stay awake — block sleep & screen blank",
                                   font=(FONT, 12), text_color=TEXT,
                                   progress_color=ACCENT, button_color=TEXT,
                                   button_hover_color=ACCENT_HI, command=self._toggle_awake)
        self.awake.grid(row=1, column=0, sticky="w", padx=16, pady=(4, 14))

        # 2 - click a point
        c2 = self._card("CLICK A POINT")
        c2.grid(row=2, column=0, sticky="ew", padx=14, pady=6)
        c2.grid_columnconfigure(0, weight=1)
        row = ctk.CTkFrame(c2, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 4))
        row.grid_columnconfigure(0, weight=1)
        self._ghost(row, "◎  Pick location", self._pick).grid(row=0, column=0, sticky="ew")
        self.coord = ctk.CTkLabel(row, text="not set", font=(MONO, 13), text_color=MUTED,
                                  fg_color=CARD2, corner_radius=8, width=96, height=32)
        self.coord.grid(row=0, column=1, padx=(10, 0))
        self._primary(c2, "Click now", self._click_now).grid(row=2, column=0, sticky="ew",
                                                             padx=16, pady=(6, 14))

        # 3 - timed click
        c3 = self._card("TIMED CLICK")
        c3.grid(row=3, column=0, sticky="ew", padx=14, pady=6)
        c3.grid_columnconfigure(0, weight=1)
        wheels = ctk.CTkFrame(c3, fg_color="transparent")
        wheels.grid(row=1, column=0, pady=(6, 2))
        self.hh = Stepper(wheels, "HOURS", 23, 0)
        self.mm = Stepper(wheels, "MINUTES", 59, 0)
        self.ss = Stepper(wheels, "SECONDS", 59, 10)
        self.hh.grid(row=0, column=0, padx=4)
        ctk.CTkLabel(wheels, text=":", font=(MONO, 26, "bold"), text_color=MUTED).grid(row=0, column=1, pady=(0, 18))
        self.mm.grid(row=0, column=2, padx=4)
        ctk.CTkLabel(wheels, text=":", font=(MONO, 26, "bold"), text_color=MUTED).grid(row=0, column=3, pady=(0, 18))
        self.ss.grid(row=0, column=4, padx=4)

        btns = ctk.CTkFrame(c3, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 6))
        btns.grid_columnconfigure((0, 1), weight=1)
        self.start_btn = self._primary(btns, "Start countdown", self._start)
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.stop_btn = self._ghost(btns, "Stop", self._stop)
        self.stop_btn.configure(state="disabled")
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.count = ctk.CTkLabel(c3, text="idle", font=(MONO, 16, "bold"), text_color=MUTED)
        self.count.grid(row=3, column=0, pady=(2, 14))

    # -- keep awake --------------------------------------------------------
    def _toggle_awake(self):
        self.win.keep_awake(bool(self.awake.get()))

    # -- picking -----------------------------------------------------------
    def _pick(self):
        self.withdraw()
        self.after(150, lambda: CrosshairPicker(self, self._picked, self.deiconify))

    def _picked(self, x, y):
        self._point = (x, y)
        self.coord.configure(text=f"{x}, {y}", text_color=ACCENT)
        self.deiconify()

    def _need_point(self):
        if not self._point:
            self.coord.configure(text="pick first!", text_color=ACCENT_HI)
            return True
        return False

    def _click_now(self):
        if self._need_point():
            return
        self.win.click(*self._point)

    # -- countdown ---------------------------------------------------------
    def _start(self):
        if self._need_point():
            return
        total = self.hh.value * 3600 + self.mm.value * 60 + self.ss.value
        if total <= 0:
            self.count.configure(text="set a time > 0", text_color=ACCENT_HI)
            return
        self._remaining = total
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._tick()

    def _tick(self):
        # SENIOR: after() loop, not a thread. Tk/CTk are single-threaded; poking
        # widgets from another thread is a classic heisenbug.
        h, rem = divmod(self._remaining, 3600)
        m, s = divmod(rem, 60)
        self.count.configure(text=f"firing in  {h:02d}:{m:02d}:{s:02d}", text_color=ACCENT)
        if self._remaining <= 0:
            self.count.configure(text="clicked  ✓", text_color=ACCENT_HI)
            self.win.click(*self._point)
            self._reset_btns()
            return
        self._remaining -= 1
        self._job = self.after(1000, self._tick)

    def _stop(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.count.configure(text="cancelled", text_color=MUTED)
        self._reset_btns()

    def _reset_btns(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def _on_close(self):
        self.win.keep_awake(False)   # SENIOR: release the power state on exit
        self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    App().mainloop()
