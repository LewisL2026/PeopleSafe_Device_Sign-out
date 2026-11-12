import csv
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime

try:
    import winsound
except ImportError:          # not on Windows
    winsound = None

# --------------------------------------------------------------------------
# SETTINGS - edit these lists to change what appears on screen
# --------------------------------------------------------------------------
TEAMS = {                     # label: (colour, text colour)
    "A": ("#1f5fd8", "white"),
    "B": ("#d62828", "white"),
    "C": ("#2a9d3f", "white"),
    "D": ("#f2c200", "black"),
    "E": ("#7b2cbf", "white"),
}

SHIFTS = {
    "Day-Shift": ("#f08c00", "white"),
    "Night-Shift": ("#2d3a8c", "white"),
}

CONDITIONS = {
    "Good": ("#2a9d3f", "white"),
    "Broken": ("#d62828", "white"),
}

# 13 devices. Rename the "Device N" ones to the real names.
DEVICES = [
    "Ground Floor", "Hanging", "Miniload", "Device 4",
    "Device 5", "Device 6", "Device 7", "Device 8",
    "Device 9", "Device 10", "Device 11", "Device 12",
    "Device 13",
]
DEVICE_COLOUR = ("#1d4e89", "white")
DEVICE_COLUMNS = 4

# Authorised people who may clear a faulty device for use again.
# PIN: name.  CHANGE THESE before going live.
AUTHORISED = {
    "1234": "Supervisor 1",
    "5678": "Supervisor 2",
}

AUTO_REFRESH_MS = 15000        # re-read the CSV every 15 s (several PCs / one file)

DATE_FORMAT = "%d-%b-%Y %H:%M"
COLUMNS = ("Engineer Name", "RM-Team", "Device-Allocation",
           "Sign-Out Date", "Sign-In Date", "Shift", "Condition",
           "Return Condition", "Fault Status", "Authorised By",
           "Authorised Date", "Notes")
# column indexes
C_NAME, C_TEAM, C_DEVICE, C_OUT, C_IN, C_SHIFT, C_COND, C_RETCOND, \
    C_FAULT, C_AUTHBY, C_AUTHDATE, C_NOTES = range(len(COLUMNS))

AVAILABLE, IN_USE, OUT_OF_SERVICE, CLEARED = (
    "Available", "In Use", "Out of Service", "Cleared")

# look of a device button that cannot be selected: state -> (bg, fg)
BLOCKED_LOOK = {
    IN_USE: ("#cfd4da", "#555555"),
    OUT_OF_SERVICE: ("#f5c6c3", "#8c1d18"),
}

BG = "#f4f6f8"

# --------------------------------------------------------------------------
# FILE LOCATION
# --------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)           # running as exe
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))  # running as .py

CSV_FILE = os.environ.get("PEOPLESAFE_CSV", os.path.join(APP_DIR, "equipment_log.csv"))


def _pad(r):
    r = list(r) + [""] * (len(COLUMNS) - len(r))
    return r[:len(COLUMNS)]


def write_all(rows):
    with open(CSV_FILE, mode="w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)


def ensure_csv():
    """Create the file, or upgrade an older 7-column log to the new layout."""
    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        write_all([])
        return
    with open(CSV_FILE, mode="r", newline="") as f:
        rows = list(csv.reader(f))
    if rows and tuple(rows[0]) != COLUMNS:
        write_all([_pad(r) for r in rows[1:] if r])


def read_all():
    """Return all data rows (no header), padded. Row index == file position."""
    ensure_csv()
    with open(CSV_FILE, mode="r", newline="") as f:
        rows = list(csv.reader(f))
    return [_pad(r) for r in rows[1:] if r]


def append_row(row):
    ensure_csv()
    with open(CSV_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow(row)


def add_note(row, text):
    """Short notes only - who/when are already in the other columns."""
    row[C_NOTES] = (row[C_NOTES] + " | " if row[C_NOTES] else "") + text


def clean_notes(text):
    """For display: hide the long '[date status - name]' stamps older versions saved."""
    return re.sub(r"\[[^\]]*\]\s*", "", text)


# --------------------------------------------------------------------------
# DEVICE STATUS  (worked out from the log, so every PC agrees)
# --------------------------------------------------------------------------
def device_states(rows):
    """device -> (state, detail, row index of the latest entry or None)"""
    last = {}
    for i, r in enumerate(rows):
        last[r[C_DEVICE]] = (i, r)

    states = {}
    for d in DEVICES:
        if d not in last:
            states[d] = (AVAILABLE, "", None)
            continue
        i, r = last[d]
        if not r[C_IN]:
            states[d] = (IN_USE, f"{r[C_NAME]} (since {r[C_OUT]})", i)
        elif "Broken" in (r[C_COND], r[C_RETCOND]):
            if r[C_FAULT] == CLEARED:
                states[d] = (AVAILABLE, "", i)
            else:                                     # old rows count as faulty
                states[d] = (OUT_OF_SERVICE, r[C_AUTHBY], i)
        else:
            states[d] = (AVAILABLE, "", i)
    return states


# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------
def beep():
    if winsound:
        try:
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass


def tint(hex_colour, amount=0.82):
    """Blend a colour with white so unselected options look faded."""
    hex_colour = hex_colour.lstrip("#")
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


class ChoiceGroup:
    """A set of big buttons where exactly one can be selected.

    Options can be blocked (e.g. device in use / out of service): they are
    greyed out and clicking them calls on_blocked instead of selecting.
    """

    def __init__(self, parent, options, on_change, columns=None,
                 width=8, height=2, font_size=18, on_blocked=None):
        self.value = ""
        self.on_change = on_change
        self.on_blocked = on_blocked
        self.options = options              # label -> (colour, text colour)
        self.states = {}                    # label -> (state, detail)
        self.buttons = {}
        columns = columns or len(options)

        for i, label in enumerate(options):
            btn = tk.Button(
                parent, text=label, width=width, height=height,
                font=("Segoe UI", font_size, "bold"),
                bd=0, highlightthickness=5, cursor="hand2",
                activebackground=options[label][0],
                command=lambda l=label: self.select(l),
            )
            btn.grid(row=i // columns, column=i % columns, padx=5, pady=5)
            self.buttons[label] = btn
        self._paint()

    def _state(self, label):
        return self.states.get(label, (AVAILABLE, ""))

    def set_states(self, states):
        self.states = {k: (v[0], v[1]) for k, v in states.items()}
        if self.value and self._state(self.value)[0] != AVAILABLE:
            self.value = ""                 # became unavailable meanwhile
        self._paint()

    def select(self, label):
        state, detail = self._state(label)
        if state != AVAILABLE:
            if self.on_blocked:
                self.on_blocked(label, state, detail)
            return
        self.value = label
        beep()
        self._paint()
        self.on_change()

    def clear(self):
        self.value = ""
        self._paint()

    def _paint(self):
        for label, btn in self.buttons.items():
            colour, text_colour = self.options[label]
            state, detail = self._state(label)
            if state != AVAILABLE:
                bg, fg = BLOCKED_LOOK.get(state, ("#cfd4da", "#555555"))
                extra = f"\n{state}"
                if state == IN_USE and detail:
                    extra += f"\n{detail.split(' (')[0]}"
                btn.config(bg=bg, fg=fg, text=label + extra,
                           highlightbackground=BG, highlightcolor=BG,
                           relief="flat", cursor="X_cursor")
            elif label == self.value:
                btn.config(bg=colour, fg=text_colour, text=f"\u2714  {label}",
                           highlightbackground="black", highlightcolor="black",
                           relief="solid", cursor="hand2")
            else:
                btn.config(bg=tint(colour), fg="#6b6b6b", text=label,
                           highlightbackground=BG, highlightcolor=BG,
                           relief="flat", cursor="hand2")


# --------------------------------------------------------------------------
# ACTIONS
# --------------------------------------------------------------------------
def set_status(message, colour="#1b5e20"):
    status_label.config(text=message, fg=colour)


def refresh_summary(*_):
    def show(v):
        return v if v else "\u2014"
    summary_var.set(
        f"Team: {show(team_group.value)}     "
        f"Name: {show(engineer_var.get().strip())}     "
        f"Shift: {show(shift_group.value)}     "
        f"Device: {show(device_group.value)}     "
        f"Condition: {show(condition_group.value)}"
    )


def clear_fields(keep_shift=True):
    engineer_var.set("")
    team_group.clear()
    device_group.clear()
    condition_group.clear()
    if not keep_shift:
        shift_group.clear()
    refresh_summary()
    engineer_entry.focus_set()


def device_blocked(label, state, detail):
    """Called when someone clicks a device that cannot be signed out."""
    beep()
    if state == IN_USE:
        messagebox.showwarning(
            "Device already in use",
            f"{label} is already signed out to:\n\n  {detail}\n\n"
            "It must be signed IN before anyone else can take it.")
    else:
        messagebox.showwarning(
            f"Device {state.lower()}",
            f"{label} is marked '{state}' and cannot be signed out.\n\n"
            "An authorised person must inspect it and clear it using the "
            "'AUTHORISED / MAINTENANCE' button before it can be used again.")


def save_entry():
    engineer = engineer_var.get().strip()
    missing = []
    if not team_group.value:
        missing.append("RM-Team")
    if not engineer:
        missing.append("Engineer Name")
    if not shift_group.value:
        missing.append("Shift")
    if not device_group.value:
        missing.append("Device")
    if not condition_group.value:
        missing.append("Condition")

    if missing:
        messagebox.showerror("Missing information",
                             "Please choose / fill in:\n\n  \u2022 " + "\n  \u2022 ".join(missing))
        return

    device = device_group.value

    # Re-check against the file right now: someone on another PC may have
    # taken the device since this screen was last refreshed.
    state, detail, _ = device_states(read_all())[device]
    if state != AVAILABLE:
        load_data()
        device_blocked(device, state, detail)
        return

    now = datetime.now().strftime(DATE_FORMAT)

    if condition_group.value == "Broken":
        if not messagebox.askyesno(
                "Report faulty device",
                f"You selected 'Broken' for {device}.\n\n"
                "A broken device is NOT signed out. It will be logged as "
                "OUT OF SERVICE until an authorised person clears it.\n\n"
                "Report it as faulty?"):
            return
        row = [engineer, team_group.value, device, now, now, shift_group.value,
               "Broken", "", OUT_OF_SERVICE, "", "", ""]
        add_note(row, "Faulty at pick-up")
        append_row(row)
        set_status(f"\u26a0 {device} reported FAULTY by {engineer} - now Out of Service",
                   "#b3261e")
        clear_fields()
        load_data()
        return

    append_row([engineer, team_group.value, device, now, "",
                shift_group.value, "Good", "", "", "", "", ""])
    set_status(f"\u2714 Signed OUT: {engineer} \u2192 {device} at {now}")
    clear_fields()
    load_data()


def ask_condition(device):
    """Big Good / Broken dialog. Returns 'Good', 'Broken' or None (cancelled)."""
    result = {"v": None}
    win = tk.Toplevel(root)
    win.title("Condition on return")
    win.configure(bg=BG)
    win.transient(root)

    tk.Label(win, text=f"What condition is\n{device} in?", bg=BG,
             font=("Segoe UI", 18, "bold")).pack(padx=40, pady=(20, 10))

    def pick(v):
        result["v"] = v
        win.destroy()

    row = tk.Frame(win, bg=BG)
    row.pack(padx=20, pady=10)
    for label in ("Good", "Broken"):
        colour, fg = CONDITIONS[label]
        tk.Button(row, text=label, width=10, height=2, bg=colour, fg=fg,
                  font=("Segoe UI", 18, "bold"), bd=0, cursor="hand2",
                  command=lambda v=label: pick(v)).pack(side=tk.LEFT, padx=8)
    tk.Button(win, text="Cancel", command=win.destroy,
              font=("Segoe UI", 11)).pack(pady=(0, 15))

    win.update_idletasks()
    try:
        win.grab_set()
    except tk.TclError:
        pass
    win.wait_window()
    return result["v"]


def sign_in_entry():
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("No selection",
                               "Click a row in the table first, then press Sign-In.")
        return

    idx = entry_of(selected[0])
    rows = read_all()
    if idx >= len(rows):
        load_data()
        return
    row = rows[idx]

    if row[C_IN]:
        messagebox.showinfo("Already signed in", "This entry is already signed in.")
        return

    name, device, out_date = row[C_NAME], row[C_DEVICE], row[C_OUT]

    if not messagebox.askyesno(
            "Confirm sign-in",
            f"Sign IN this device?\n\n"
            f"  Device:   {device}\n"
            f"  Engineer: {name}\n"
            f"  Signed out: {out_date}\n\n"
            "Is this the correct device and person?"):
        return

    condition = ask_condition(device)
    if condition is None:
        return

    now = datetime.now().strftime(DATE_FORMAT)
    row[C_IN] = now
    row[C_RETCOND] = condition
    if condition == "Broken":
        row[C_FAULT] = OUT_OF_SERVICE
        add_note(row, "Returned broken")

    write_all(rows)

    if condition == "Broken":
        set_status(f"\u26a0 Signed IN: {name} \u2190 {device} at {now} - BROKEN, "
                   "device is now Out of Service", "#b3261e")
    else:
        set_status(f"\u2714 Signed IN: {name} \u2190 {device} at {now}")
    beep()
    load_data()


# --------------------------------------------------------------------------
# AUTHORISED / MAINTENANCE
# --------------------------------------------------------------------------
def open_maintenance():
    pin = simpledialog.askstring("Authorised access", "Enter authorised PIN:",
                                 show="*", parent=root)
    if pin is None:
        return
    who = AUTHORISED.get(pin.strip())
    if not who:
        messagebox.showerror("Access denied", "PIN not recognised.")
        return

    win = tk.Toplevel(root)
    win.title("Authorised / Maintenance")
    win.geometry("1100x480")
    win.configure(bg=BG)
    win.transient(root)

    tk.Label(win, text="Faulty devices", bg=BG,
             font=("Segoe UI", 20, "bold")).pack(pady=(10, 0))
    tk.Label(win, text=f"Logged in as: {who}", bg=BG, fg="#444444",
             font=("Segoe UI", 12)).pack()

    cols = ("Device", "Status", "Reported by", "Date", "Authorised By", "Notes")
    tv = ttk.Treeview(win, columns=cols, show="headings", selectmode="browse", height=9)
    widths = (140, 120, 140, 130, 130, 420)
    for c, w in zip(cols, widths):
        tv.heading(c, text=c)
        tv.column(c, width=w, anchor="w")
    tv.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

    def populate():
        for item in tv.get_children():
            tv.delete(item)
        rows = read_all()
        for dev, (state, _d, i) in device_states(rows).items():
            if state == OUT_OF_SERVICE:
                r = rows[i]
                tv.insert("", tk.END, iid=str(i),
                          values=(dev, state, r[C_NAME], r[C_IN], r[C_AUTHBY],
                                  clean_notes(r[C_NOTES])))

    def clear_for_use():
        sel = tv.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a device in the list first.",
                                   parent=win)
            return
        i = int(sel[0])
        rows = read_all()
        row = rows[i]
        device = row[C_DEVICE]

        if device_states(rows)[device][0] != OUT_OF_SERVICE:
            messagebox.showinfo("Already cleared",
                                f"{device} is no longer out of service.", parent=win)
            populate()
            load_data()
            return

        note = simpledialog.askstring(
            device, "Inspection result - what was checked / fixed?\n"
                    "(required before the device can be used again)", parent=win)
        if note is None:
            return
        note = note.strip()
        if not note:
            messagebox.showerror("Note required",
                                 "Please record the inspection result.", parent=win)
            return

        if not messagebox.askyesno(
                "Clear for use",
                f"Confirm {device} has been inspected and is safe to use?",
                parent=win):
            return

        row[C_FAULT] = CLEARED
        row[C_AUTHBY] = who
        row[C_AUTHDATE] = datetime.now().strftime(DATE_FORMAT)
        add_note(row, f"Cleared: {note}")
        write_all(rows)

        set_status(f"\u2714 {device} cleared for use by {who}")
        beep()
        populate()
        load_data()

    btns = tk.Frame(win, bg=BG)
    btns.pack(pady=(0, 12))
    tk.Button(btns, text="CLEAR FOR USE", font=("Segoe UI", 13, "bold"),
              bg="#1b7f2a", fg="white", bd=0, padx=14, pady=8, cursor="hand2",
              command=clear_for_use).pack(side=tk.LEFT, padx=8)
    tk.Button(btns, text="Close", font=("Segoe UI", 12), padx=10, pady=6,
              command=win.destroy).pack(side=tk.LEFT, padx=8)

    populate()
    if not tv.get_children():
        tk.Label(win, text="No faulty devices right now.", bg=BG, fg="#2a9d3f",
                 font=("Segoe UI", 12, "bold")).pack()


# --------------------------------------------------------------------------
# TABLE / REFRESH
# --------------------------------------------------------------------------
ROW_GROUPS = {}          # entry id -> all table lines that belong to it
LAST_WRAP = [0]          # pixel width the notes were last wrapped to


def _hard_break(word, width_px):
    """Split one over-long word into pieces that fit."""
    pieces, cur = [], ""
    for ch in word:
        if cur and note_font.measure(cur + ch) > width_px:
            pieces.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        pieces.append(cur)
    return pieces


def wrap_notes(text, width_px):
    """Wrap notes to the column width; each stamped note starts a new line."""
    lines = []
    for note in text.split(" | "):
        cur = ""
        for word in note.split():
            if note_font.measure(word) > width_px:
                if cur:
                    lines.append(cur)
                    cur = ""
                parts = _hard_break(word, width_px)
                lines.extend(parts[:-1])
                cur = parts[-1]
                continue
            trial = f"{cur} {word}" if cur else word
            if cur and note_font.measure(trial) > width_px:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
    return lines


def entry_of(iid):
    """Table line id -> log entry index ('12.2' is line 3 of entry 12)."""
    return int(str(iid).split(".")[0])


def load_data():
    selected = tree.selection()
    selected_entry = str(entry_of(selected[0])) if selected else None
    for item in tree.get_children():
        tree.delete(item)
    ROW_GROUPS.clear()

    rows = read_all()
    states = device_states(rows)
    device_group.set_states({d: (s[0], s[1]) for d, s in states.items()})
    refresh_summary()

    width_px = max(80, tree.column("Notes", "width") - 16)
    LAST_WRAP[0] = width_px

    faulty_idx = {s[2] for s in states.values() if s[0] == OUT_OF_SERVICE}
    for i in range(len(rows) - 1, -1, -1):             # newest first
        row = rows[i]
        if not row[C_IN]:
            tag = "out"
        elif i in faulty_idx:
            tag = "fault"
        else:
            tag = ""
        lines = wrap_notes(clean_notes(row[C_NOTES]), width_px) or [""]
        ids = []
        for k, line in enumerate(lines):
            iid = str(i) if k == 0 else f"{i}.{k}"
            if k == 0:
                values = row[:C_NOTES] + [line]
            else:                                       # continuation line
                values = [""] * C_NOTES + [line]
            tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
            ids.append(iid)
        ROW_GROUPS[str(i)] = ids

    if selected_entry in ROW_GROUPS:
        tree.selection_set(ROW_GROUPS[selected_entry])


_resize_job = [None]


def on_table_resize(_event=None):
    """Re-wrap the notes when the window (and so the Notes column) changes size."""
    if _resize_job[0]:
        root.after_cancel(_resize_job[0])

    def redo():
        _resize_job[0] = None
        if abs(max(80, tree.column("Notes", "width") - 16) - LAST_WRAP[0]) > 4:
            load_data()
    _resize_job[0] = root.after(200, redo)


def on_select(_event=None):
    """Clicking any line of a wrapped entry selects the whole entry."""
    sel = tree.selection()
    if not sel:
        return
    focus = tree.focus()
    entry = str(entry_of(focus if focus in sel else sel[0]))
    wanted = ROW_GROUPS.get(entry, [])
    if wanted and set(sel) != set(wanted):
        tree.selection_set(wanted)


def auto_refresh():
    try:
        load_data()
    finally:
        root.after(AUTO_REFRESH_MS, auto_refresh)


# --------------------------------------------------------------------------
# WINDOW
# --------------------------------------------------------------------------
root = tk.Tk()
root.title("PeopleSafe - MySOS Device Sign-Out")
root.geometry("1400x900")
root.configure(bg=BG)

engineer_var = tk.StringVar()
summary_var = tk.StringVar()

# Draggable divider: grab the bar between the controls and the table and
# drag it up (bigger table) or down (bigger controls).
paned = tk.PanedWindow(root, orient=tk.VERTICAL, bg="#b0b7c0",
                       sashwidth=12, sashrelief="raised", sashcursor="sb_v_double_arrow")
paned.pack(fill=tk.BOTH, expand=True)

top = tk.Frame(paned, bg=BG)
paned.add(top, minsize=120, stretch="never")

tk.Label(top, text="MySOS Device Sign-Out", bg=BG,
         font=("Segoe UI", 22, "bold")).pack(pady=(4, 0))


def card(parent, title):
    frame = tk.LabelFrame(parent, text=f" {title} ", bg=BG,
                          font=("Segoe UI", 16, "bold"), padx=10, pady=8)
    return frame


body = tk.Frame(top, bg=BG)
body.pack(fill=tk.X, padx=15, pady=2)

# ---- Left column: team, name, shift -------------------------------------
left = tk.Frame(body, bg=BG)
left.pack(side=tk.LEFT, anchor="n")

team_card = card(left, "1. RM-Team")
team_card.pack(fill=tk.X, pady=4)
team_group = ChoiceGroup(team_card, TEAMS, refresh_summary,
                         width=3, height=1, font_size=20)

name_card = card(left, "2. Engineer Name")
name_card.pack(fill=tk.X, pady=4)
engineer_entry = tk.Entry(name_card, textvariable=engineer_var,
                          font=("Segoe UI", 20), width=26)
engineer_entry.pack(fill=tk.X)
engineer_var.trace_add("write", refresh_summary)

shift_card = card(left, "3. Shift")
shift_card.pack(fill=tk.X, pady=4)
shift_group = ChoiceGroup(shift_card, SHIFTS, refresh_summary,
                          width=11, height=1, font_size=18)

# ---- Middle: devices ----------------------------------------------------
device_card = card(body, "4. Select Device")
device_card.pack(side=tk.LEFT, anchor="n", padx=20, pady=4)
device_group = ChoiceGroup(device_card, {d: DEVICE_COLOUR for d in DEVICES},
                           refresh_summary, columns=DEVICE_COLUMNS,
                           width=13, height=3, font_size=12,
                           on_blocked=device_blocked)

# ---- Right: condition + actions ----------------------------------------
right = tk.Frame(body, bg=BG)
right.pack(side=tk.RIGHT, anchor="n")

cond_card = card(right, "5. Condition")
cond_card.pack(fill=tk.X, pady=4)
condition_group = ChoiceGroup(cond_card, CONDITIONS, refresh_summary,
                              columns=1, width=12, height=2, font_size=18)

signout_button = tk.Button(
    right, text="SIGN-OUT", font=("Segoe UI", 20, "bold"),
    bg="#1b7f2a", fg="white", activebackground="#14661f", activeforeground="white",
    width=14, height=2, bd=0, cursor="hand2",
    command=lambda: [beep(), save_entry()])
signout_button.pack(pady=(10, 4))

signin_button = tk.Button(
    right, text="SIGN-IN\n(select a row below)", font=("Segoe UI", 16, "bold"),
    bg="#b3261e", fg="white", activebackground="#8c1d18", activeforeground="white",
    width=18, height=2, bd=0, cursor="hand2",
    command=lambda: [beep(), sign_in_entry()])
signin_button.pack(pady=4)

maint_button = tk.Button(
    right, text="AUTHORISED /\nMAINTENANCE", font=("Segoe UI", 13, "bold"),
    bg="#444b55", fg="white", activebackground="#2c3138", activeforeground="white",
    width=22, height=2, bd=0, cursor="hand2", command=open_maintenance)
maint_button.pack(pady=4)

# ---- Summary + status ---------------------------------------------------
tk.Label(top, textvariable=summary_var, bg="#e3ebf5", fg="#1a1a1a",
         font=("Segoe UI", 14), anchor="w", padx=12, pady=6).pack(fill=tk.X, padx=15, pady=(6, 0))

status_label = tk.Label(top, text="Ready.", bg=BG, fg="#444444",
                        font=("Segoe UI", 13, "bold"), anchor="w", padx=12)
status_label.pack(fill=tk.X, padx=15)

# ---- Table ---------------------------------------------------------------
table_frame = tk.Frame(paned, bg=BG)
paned.add(table_frame, minsize=120, stretch="always")

style = ttk.Style()
style.configure("Treeview", rowheight=24, font=("Segoe UI", 10))
note_font = tkfont.Font(family="Segoe UI", size=10)
style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

tree = ttk.Treeview(table_frame, columns=COLUMNS, show="headings", selectmode="extended")
# Fixed column widths that fit the window; only Notes stretches with it.
COL_WIDTHS = (120, 70, 120, 130, 130, 90, 80, 125, 110, 110, 130, 150)
for col, w in zip(COLUMNS, COL_WIDTHS):
    tree.heading(col, text=col)
    tree.column(col, width=w, minwidth=w, anchor="w",
                stretch=(col == "Notes"))

# Stop people dragging the column borders to resize / push columns off screen.
tree.bind("<Button-1>",
          lambda e: "break" if tree.identify_region(e.x, e.y) == "separator" else None)
tree.bind("<B1-Motion>",
          lambda e: "break" if tree.identify_region(e.x, e.y) == "separator" else None)
tree.bind("<<TreeviewSelect>>", on_select)
tree.bind("<Configure>", on_table_resize)
tree.tag_configure("out", background="#fff3cd")      # still signed out
tree.tag_configure("fault", background="#f8d7da")    # device faulty / not cleared

yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=yscroll.set)
yscroll.pack(side=tk.RIGHT, fill=tk.Y)
tree.pack(fill=tk.BOTH, expand=True)

refresh_summary()
load_data()
engineer_entry.focus_set()
root.after(AUTO_REFRESH_MS, auto_refresh)
root.mainloop()
