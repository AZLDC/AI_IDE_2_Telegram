#!/usr/bin/env python3
"""Frameless desktop prompt. Each received status is shown at once."""

import socket
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROMPT_FILE = ROOT / "local_prompt.txt"
BACKGROUND = ROOT / "message_BG.png"
INSTANCE_PORT = 47631


def _drop_console() -> None:
    """A double-clicked .pyw can still be started by python.exe and keep a console open."""
    if sys.platform != "win32":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    if not kernel32.GetConsoleWindow():
        return
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if pythonw.exists():
        import subprocess

        subprocess.Popen(
            [str(pythonw), str(Path(__file__).resolve()), *sys.argv[1:]],
            close_fds=True,
            creationflags=0x00000008,
        )
        raise SystemExit(0)
    ctypes.windll.user32.ShowWindow(kernel32.GetConsoleWindow(), 0)
    kernel32.FreeConsole()


def main() -> None:
    _drop_console()
    run_app()


def acquire_instance() -> socket.socket | None:
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        holder.bind(("127.0.0.1", INSTANCE_PORT))
    except OSError:
        holder.close()
        return None
    holder.listen(1)
    return holder


def load_background(path: Path):
    """Use the picture's own alpha. Do not flatten it and do not fade the whole window."""
    from PIL import Image

    return Image.open(path).convert("RGBA")


def compose_card(background, message: str, stamp: str):
    """Draw the status on a copy of the background, leaving the picture alpha intact."""
    from PIL import Image, ImageDraw, ImageFont

    image = background.copy()
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    margin = 28
    message_font = _ui_font(ImageFont, 18)
    time_font = _ui_font(ImageFont, 13)
    message_lines = _wrap_text(draw, message, message_font, width - margin * 2)
    time_line = stamp.split(".")[0]
    gap = 6
    line_gap = 2
    message_height = sum(draw.textbbox((0, 0), line, font=message_font)[3] for line in message_lines)
    message_height += line_gap * (len(message_lines) - 1)
    time_height = draw.textbbox((0, 0), time_line, font=time_font)[3]
    block_height = message_height + gap + time_height
    top = max(margin, (height - block_height) // 2)
    boxes = []
    cursor = top
    for line in message_lines:
        box = draw.textbbox((0, 0), line, font=message_font)
        line_width = box[2] - box[0]
        line_height = box[3] - box[1]
        origin_x = (width - line_width) // 2
        draw.text((origin_x, cursor), line, font=message_font, fill=(17, 17, 17, 255))
        boxes.append((origin_x, cursor, line_width, line_height))
        cursor += line_height + line_gap
    time_box = draw.textbbox((0, 0), time_line, font=time_font)
    time_width = time_box[2] - time_box[0]
    time_height = time_box[3] - time_box[1]
    time_x = (width - time_width) // 2
    time_y = top + message_height + gap
    draw.text((time_x, time_y), time_line, font=time_font, fill=(51, 51, 51, 255))
    boxes.append((time_x, time_y, time_width, time_height))
    return Image.alpha_composite(image, overlay), boxes


def _ui_font(image_font, size: int):
    if sys.platform == "darwin":
        candidates = ["/System/Library/Fonts/PingFang.ttc"]
    else:
        candidates = [r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\msjh.ttf"]
    for candidate in candidates:
        if Path(candidate).exists():
            return image_font.truetype(candidate, size)
    return image_font.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text:
        trial = current + character
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = character
    if current:
        lines.append(current)
    return lines or [""]


def tray_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 18, 58, 46), radius=8, fill="white", outline="black", width=3)
    return image


def _present_alpha(root, image) -> None:
    """Show the card with the picture's alpha, including partial transparency."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = root.winfo_id()
    parent = user32.GetParent(hwnd)
    if parent:
        hwnd = parent
    ex_style = -20
    layered = 0x00080000
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        get_long = user32.GetWindowLongPtrW
        set_long = user32.SetWindowLongPtrW
        get_long.restype = ctypes.c_void_p
        set_long.restype = ctypes.c_void_p
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    else:
        get_long = user32.GetWindowLongW
        set_long = user32.SetWindowLongW
    current = get_long(hwnd, ex_style) or 0
    set_long(hwnd, ex_style, current | layered)

    width, height = image.size
    raw = image.tobytes()
    pixels = bytearray(len(raw))
    for index in range(0, len(raw), 4):
        red, green, blue, alpha = raw[index : index + 4]
        pixels[index] = blue * alpha // 255
        pixels[index + 1] = green * alpha // 255
        pixels[index + 2] = red * alpha // 255
        pixels[index + 3] = alpha

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class SIZE(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [
            ("BlendOp", ctypes.c_byte),
            ("BlendFlags", ctypes.c_byte),
            ("SourceConstantAlpha", ctypes.c_byte),
            ("AlphaFormat", ctypes.c_byte),
        ]

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    screen_dc = user32.GetDC(0)
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(memory_dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, bytes(pixels), len(pixels))
    previous = gdi32.SelectObject(memory_dc, bitmap)
    size = SIZE(width, height)
    origin = POINT(0, 0)
    blend = BLENDFUNCTION(0, 0, 255, 1)
    user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND,
        wintypes.HDC,
        ctypes.c_void_p,
        ctypes.POINTER(SIZE),
        wintypes.HDC,
        ctypes.POINTER(POINT),
        wintypes.DWORD,
        ctypes.POINTER(BLENDFUNCTION),
        wintypes.DWORD,
    ]
    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    user32.UpdateLayeredWindow(hwnd, screen_dc, None, ctypes.byref(size), memory_dc, ctypes.byref(origin), 0, ctypes.byref(blend), 2)
    gdi32.SelectObject(memory_dc, previous)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(0, screen_dc)


class PromptWindow:
    """Draggable card. It listens only while this program is running."""

    def __init__(self, root, background: Path) -> None:
        import tkinter as tk

        self.root = root
        self._tk = tk
        self._drag_x = 0
        self._drag_y = 0
        self._visible = True
        self._seen = ""
        self._alive = True
        self.icon = None

        self._background = load_background(background)
        self._message = "尚無提示"
        self._stamp = "—"
        self._boxes: list[tuple[int, int, int, int]] = []
        width, height = self._background.size
        self.root.overrideredirect(True)
        self.root.configure(bg="#ffffff")
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        origin_x = max(0, (screen_w - width) // 2)
        origin_y = max(0, screen_h - height - 96)
        self.root.geometry(f"{width}x{height}+{origin_x}+{origin_y}")
        self.root.bind("<ButtonPress-1>", self._press)
        self.root.bind("<B1-Motion>", self._drag)
        self.root.configure(cursor="fleur")
        self.root.update_idletasks()
        self.root.update()
        self._paint()
        self.raise_top()

    def raise_top(self) -> None:
        self.root.attributes("-topmost", True)
        self.root.lift()

    def show_text(self, message: str, stamp: str) -> None:
        self._message = message
        self._stamp = stamp
        self._paint()
        if self._visible:
            self.raise_top()

    def show(self) -> None:
        self.root.deiconify()
        self._visible = True
        self._paint()
        self.raise_top()

    def _paint(self) -> None:
        image, self._boxes = compose_card(self._background, self._message, self._stamp)
        if sys.platform == "win32":
            _present_alpha(self.root, image)
            return
        self._paint_with_widgets(image)

    def _paint_with_widgets(self, image) -> None:
        from PIL import ImageTk

        photo = ImageTk.PhotoImage(image)
        self._photo = photo
        if not hasattr(self, "_backdrop"):
            import tkinter as tk

            self._backdrop = tk.Label(self.root, bd=0, bg="#ffffff")
            self._backdrop.place(x=0, y=0, relwidth=1, relheight=1)
            self._backdrop.bind("<ButtonPress-1>", self._press)
            self._backdrop.bind("<B1-Motion>", self._drag)
        self._backdrop.configure(image=photo)

    def hide(self) -> None:
        self.root.withdraw()
        self._visible = False

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def close(self) -> None:
        self._alive = False
        icon = self.icon
        self.icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        self.root.quit()
        self.root.destroy()

    def poll(self) -> None:
        if not self._alive:
            return
        from local_prompt import read_prompt

        try:
            current = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else ""
        except OSError:
            current = self._seen
        if current and current != self._seen:
            self._seen = current
            parsed = read_prompt(PROMPT_FILE)
            if parsed is not None:
                stamp, _status, message = parsed
                self.show_text(message or _status, stamp)
        self.root.after(50, self.poll)

    def _press(self, event) -> None:
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _drag(self, event) -> None:
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")


def start_tray(root, window: PromptWindow):
    import pystray

    menu = pystray.Menu(
        pystray.MenuItem("顯示/隱藏狀態", lambda _icon, _item: root.after(0, window.toggle)),
        pystray.MenuItem("離開", lambda _icon, _item: root.after(0, window.close)),
    )
    icon = pystray.Icon("ai-status-prompt", tray_image(), "AI 狀態提示", menu)
    window.icon = icon
    # Windows runs the tray on its own thread. macOS reuses Tk's AppKit loop.
    icon.run_detached()
    return icon


def run_app() -> None:
    import tkinter as tk

    holder = acquire_instance()
    if holder is None:
        return
    root = tk.Tk()
    window = PromptWindow(root, BACKGROUND)
    start_tray(root, window)
    window.poll()
    try:
        root.mainloop()
    finally:
        holder.close()


if __name__ == "__main__":
    main()
