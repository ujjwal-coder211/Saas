"""System tools for Sarva Agent (Harness) — paper §4.2.3.

open_app, manage_clipboard, notify, screenshot_region. These touch the host OS, so
they only work on a desktop session; on a headless server each returns a clean
``ok: False`` with the reason instead of raising. No third-party deps are required —
clipboard/notify fall back to native OS utilities, with optional pyperclip/mss used
when present for reliability.
"""

from __future__ import annotations

import base64
import platform
import shutil
import subprocess
from typing import Any

_OS = platform.system().lower()  # 'windows' | 'darwin' | 'linux'
_RUN_TIMEOUT = 15


def _run(cmd: list[str], *, capture: bool = True, text_input: str | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            input=text_input,
            timeout=_RUN_TIMEOUT,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except Exception as exc:  # pragma: no cover - defensive
        return 1, str(exc)


def open_app(name: str) -> dict[str, Any]:
    """Open an application by name (macOS ``open -a`` / Linux ``xdg-open`` / Windows ``start``)."""
    if not name:
        return {"ok": False, "error": "app name required"}
    if _OS == "darwin":
        code, out = _run(["open", "-a", name])
    elif _OS == "linux":
        launcher = "gtk-launch" if shutil.which("gtk-launch") else "xdg-open"
        code, out = _run([launcher, name])
    elif _OS == "windows":
        # `start` is a cmd builtin; shell=True is required for it.
        try:
            subprocess.run(f'start "" "{name}"', shell=True, timeout=_RUN_TIMEOUT)
            code, out = 0, ""
        except Exception as exc:
            code, out = 1, str(exc)
    else:
        return {"ok": False, "error": f"Unsupported OS: {_OS}"}
    return {"ok": code == 0, "app": name, "output": out.strip() or None}


def manage_clipboard(action: str, content: str = "") -> dict[str, Any]:
    """Read or write the system clipboard. action: 'read' | 'write'."""
    action = (action or "").lower()
    if action not in ("read", "write"):
        return {"ok": False, "error": "action must be 'read' or 'write'"}

    # Prefer pyperclip when available (most reliable, cross-platform).
    try:
        import pyperclip  # type: ignore

        if action == "write":
            pyperclip.copy(content)
            return {"ok": True, "action": "write", "bytes": len(content)}
        return {"ok": True, "action": "read", "content": pyperclip.paste()}
    except Exception:
        pass

    # Native fallbacks.
    if action == "write":
        if _OS == "darwin":
            code, out = _run(["pbcopy"], text_input=content)
        elif _OS == "linux":
            tool = ["xclip", "-selection", "clipboard"] if shutil.which("xclip") else ["xsel", "-b"]
            code, out = _run(tool, text_input=content)
        elif _OS == "windows":
            code, out = _run(["clip"], text_input=content)
        else:
            return {"ok": False, "error": f"Unsupported OS: {_OS}"}
        return {"ok": code == 0, "action": "write", "bytes": len(content), "error": out or None}

    # read
    if _OS == "darwin":
        code, out = _run(["pbpaste"])
    elif _OS == "linux":
        tool = ["xclip", "-selection", "clipboard", "-o"] if shutil.which("xclip") else ["xsel", "-b", "-o"]
        code, out = _run(tool)
    elif _OS == "windows":
        code, out = _run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
    else:
        return {"ok": False, "error": f"Unsupported OS: {_OS}"}
    if code != 0:
        return {"ok": False, "error": out or "clipboard read failed"}
    return {"ok": True, "action": "read", "content": out.rstrip("\n")}


def notify(title: str, message: str) -> dict[str, Any]:
    """System notification via the OS notification center."""
    title = title or "Saira"
    if _OS == "darwin":
        script = f'display notification "{message}" with title "{title}"'
        code, out = _run(["osascript", "-e", script])
    elif _OS == "linux":
        code, out = _run(["notify-send", title, message])
    elif _OS == "windows":
        ps = (
            "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
            "$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
            f"$n.ShowBalloonTip(5000,'{title}','{message}',"
            "[System.Windows.Forms.ToolTipIcon]::Info)"
        )
        code, out = _run(["powershell", "-NoProfile", "-Command", ps])
    else:
        return {"ok": False, "error": f"Unsupported OS: {_OS}"}
    return {"ok": code == 0, "title": title, "error": out or None}


def screenshot_region(x: int, y: int, w: int, h: int) -> dict[str, Any]:
    """Capture a screen region → base64 PNG. Used for visual verification of system state."""
    if w <= 0 or h <= 0:
        return {"ok": False, "error": "w and h must be positive"}
    # Try mss first, then Pillow's ImageGrab.
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            raw = sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
            import mss.tools  # type: ignore

            png = mss.tools.to_png(raw.rgb, raw.size)
            return {"ok": True, "format": "png", "base64": base64.b64encode(png).decode("ascii")}
    except Exception:
        pass
    try:
        from PIL import ImageGrab  # type: ignore
        import io

        img = ImageGrab.grab(bbox=(int(x), int(y), int(x + w), int(y + h)))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {"ok": True, "format": "png", "base64": base64.b64encode(buf.getvalue()).decode("ascii")}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Screen capture needs mss or Pillow on a desktop session ({exc})",
        }
