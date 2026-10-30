import csv
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
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

DATE_FORMAT = "%d-%b-%Y %H:%M"
COLUMNS = ("Engineer Name", "RM-Team", "Device-Allocation",
           "Sign-Out Date", "Sign-In Date", "Shift", "Condition")

BG = "#f4f6f8"

# --------------------------------------------------------------------------
# FILE LOCATION
# --------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)           # running as exe
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))  # running as .py

CSV_FILE = os.environ.get("PEOPLESAFE_CSV", os.path.join(APP_DIR, "equipment_log.csv"))


def ensure_csv():
    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        with open(CSV_FILE, mode="w", newline="") as f:
            csv.writer(f).writerow(COLUMNS)


def read_rows():
    """Return data rows (no header), each padded to the right length."""
    ensure_csv()
    with open(CSV_FILE, mode="r", newline="") as f:
        rows = list(csv.reader(f))
    data = rows[1:] if rows else []
    padded = []
    for r in data:
        if not r:
            continue
        r = r + [""] * (len(COLUMNS) - len(r))
        padded.append(r[:len(COLUMNS)])
    return padded


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
    """A set of big buttons where exactly one can be selected."""

    def __init__(self, parent, options, on_change, columns=None,
                 width=8, height=2, font_size=18):
        self.value = ""
        self.on_change = on_change
        self.options = options              # label -> (colour, text colour)
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

    def select(self, label):
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
            if label == self.value:
                btn.config(bg=colour, fg=text_colour, text=f"\u2714  {label}",
                           highlightbackground="black", highlightcolor="black",
                           relief="solid")
            else:
                btn.config(bg=tint(colour), fg="#6b6b6b", text=label,
                           highlightbackground=BG, highlightcolor=BG,
                           relief="flat")


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

    signout_date = datetime.now().strftime(DATE_FORMAT)
    ensure_csv()
    with open(CSV_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow([engineer, team_group.value, device_group.value,
                                signout_date, "", shift_group.value,
                                condition_group.value])

    set_status(f"\u2714 Signed OUT: {engineer} \u2192 {device_group.value} at {signout_date}")
    clear_fields()
    load_data()


def sign_in_entry():
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("No selection",
                               "Click a row in the table first, then press Sign-In.")
        return

    values = list(tree.item(selected[0], "values"))
    values += [""] * (len(COLUMNS) - len(values))
    name, _team, device, signout_date, signin_date = values[:5]

    if signin_date:
        messagebox.showinfo("Already signed in", "This entry is already signed in.")
        return

    now = datetime.now().strftime(DATE_FORMAT)

    ensure_csv()
    with open(CSV_FILE, mode="r", newline="") as f:
        rows = list(csv.reader(f))

    updated = False
    for row in rows[1:]:
        row += [""] * (len(COLUMNS) - len(row))
        if (row[0] == name and row[2] == device and row[3] == signout_date
                and not row[4] and not updated):
            row[4] = now
            updated = True

    if not updated:
        messagebox.showerror("Not found", "Could not find that entry in the log.")
        return

    with open(CSV_FILE, mode="w", newline="") as f:
        csv.writer(f).writerows(rows)

    set_status(f"\u2714 Signed IN: {name} \u2190 {device} at {now}")
    beep()
    load_data()


def load_data():
    for item in tree.get_children():
        tree.delete(item)
    for row in reversed(read_rows()):          # newest first
        tag = "out" if not row[4] else ""
        tree.insert("", tk.END, values=row, tags=(tag,))


# --------------------------------------------------------------------------
# WINDOW
# --------------------------------------------------------------------------
root = tk.Tk()
root.title("PeopleSafe - MySOS Device Sign-Out")
root.geometry("1400x850")
root.configure(bg=BG)

engineer_var = tk.StringVar()
summary_var = tk.StringVar()

tk.Label(root, text="MySOS Device Sign-Out", bg=BG,
         font=("Segoe UI", 28, "bold")).pack(pady=(8, 2))


def card(parent, title):
    frame = tk.LabelFrame(parent, text=f" {title} ", bg=BG,
                          font=("Segoe UI", 16, "bold"), padx=10, pady=8)
    return frame


body = tk.Frame(root, bg=BG)
body.pack(fill=tk.X, padx=15, pady=5)

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
                           width=13, height=3, font_size=14)

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

# ---- Summary + status ---------------------------------------------------
tk.Label(root, textvariable=summary_var, bg="#e3ebf5", fg="#1a1a1a",
         font=("Segoe UI", 14), anchor="w", padx=12, pady=6).pack(fill=tk.X, padx=15, pady=(6, 0))

status_label = tk.Label(root, text="Ready.", bg=BG, fg="#444444",
                        font=("Segoe UI", 13, "bold"), anchor="w", padx=12)
status_label.pack(fill=tk.X, padx=15)

# ---- Table ---------------------------------------------------------------
table_frame = tk.Frame(root, bg=BG)
table_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(4, 10))

style = ttk.Style()
style.configure("Treeview", rowheight=28, font=("Segoe UI", 11))
style.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"))

tree = ttk.Treeview(table_frame, columns=COLUMNS, show="headings", selectmode="browse")
for col in COLUMNS:
    tree.heading(col, text=col)
    tree.column(col, width=150, anchor="w")
tree.tag_configure("out", background="#fff3cd")      # still signed out

scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=scroll.set)
scroll.pack(side=tk.RIGHT, fill=tk.Y)
tree.pack(fill=tk.BOTH, expand=True)

refresh_summary()
load_data()
engineer_entry.focus_set()
root.mainloop()