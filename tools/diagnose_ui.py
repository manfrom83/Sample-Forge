"""
Diagnostic script to inspect ttk button layout/fonts/scaling.

Builds the main window, finds the "Launch/Reload Server" button, and prints:
- Tk scaling, current theme
- Style layouts for TButton and Accent.TButton
- Style configs for TButton and Accent.TButton
- Effective font metrics (linespace/ascent/descent)
- Widget style, state, padding, and geometry
"""

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import sys


def _walk(w):
    yield w
    try:
        for c in w.winfo_children():
            yield from _walk(c)
    except Exception:
        return


def main():
    # Lazy import project components to avoid side-effects before Tk root exists
    from managers.api_config_manager import ParameterConfig
    from utils.api_client import LLMClient
    from ui.main_window import ParameterUI

    config = ParameterConfig()
    client = LLMClient()
    ui = ParameterUI(config, client, cache_manager=None)
    root = ui.create_main_window()

    # Force geometry calculation
    root.update_idletasks()
    try:
        root.update()
    except Exception:
        pass

    style = ttk.Style()
    current_theme = style.theme_use()
    scaling = root.tk.call('tk', 'scaling')

    # Try to locate the Launch/Reload Server button
    launch_btn = None
    for w in _walk(root):
        try:
            if isinstance(w, ttk.Button):
                txt = w.cget('text')
                if isinstance(txt, str) and txt.strip().lower() == 'launch/reload server':
                    launch_btn = w
                    break
        except Exception:
            continue

    print("=== Tk/Theme ===")
    print(f"tk scaling: {scaling}")
    print(f"theme: {current_theme}")

    print("\n=== Style Layouts ===")
    try:
        print("TButton:", style.layout('TButton'))
    except Exception as e:
        print("TButton layout error:", e)
    try:
        print("Accent.TButton:", style.layout('Accent.TButton'))
    except Exception as e:
        print("Accent.TButton layout error:", e)

    print("\n=== Style Config ===")
    try:
        print("TButton:", style.configure('TButton'))
    except Exception as e:
        print("TButton config error:", e)
    try:
        print("Accent.TButton:", style.configure('Accent.TButton'))
    except Exception as e:
        print("Accent.TButton config error:", e)

    if launch_btn is None:
        print("\n[WARN] Launch/Reload Server button not found. Is the Server Config tab created?")
        print("The app creates it on startup; if not found, layout may differ.")
        root.destroy()
        return 1

    # Button info
    root.update_idletasks()
    try:
        root.update()
    except Exception:
        pass
    btn_style = launch_btn.cget('style') or 'TButton'
    btn_state = launch_btn.state()
    # Widget-specific padding (may be '')
    try:
        btn_padding = launch_btn.cget('padding')
    except Exception:
        btn_padding = ''

    # Effective font name lookup
    font_name = style.lookup(btn_style, 'font') or style.lookup('TButton', 'font') or style.lookup('.', 'font')
    # Fall back to default if lookup fails
    if not font_name:
        font_name = tkfont.nametofont('TkDefaultFont').actual('family')
    try:
        fnt = tkfont.nametofont(font_name) if isinstance(font_name, str) and font_name in tkfont.names() else tkfont.nametofont('TkDefaultFont')
    except Exception:
        fnt = tkfont.nametofont('TkDefaultFont')

    metrics = {k: fnt.metrics(k) for k in ('ascent', 'descent', 'linespace')}
    bbox = (launch_btn.winfo_width(), launch_btn.winfo_height())

    print("\n=== Launch/Reload Button ===")
    print(f"style: {btn_style}")
    print(f"state: {btn_state}")
    print(f"widget padding: {btn_padding!r}")
    print(f"font: {fnt.actual()}")
    print(f"font metrics: {metrics}")
    print(f"widget size (w,h): {bbox}")

    # Derive a quick heuristic for clipping risk
    try:
        # Parse padding into (l,t,r,b) or (x,y)
        def _parse_pad(val):
            if not val:
                return (0, 0, 0, 0)
            try:
                parts = [int(float(x)) for x in str(val).replace(',', ' ').split() if x.strip()]
                if len(parts) == 1:
                    return (parts[0], parts[0], parts[0], parts[0])
                if len(parts) == 2:
                    return (parts[0], parts[1], parts[0], parts[1])
                if len(parts) == 4:
                    return tuple(parts[:4])
                return (0, 0, 0, 0)
            except Exception:
                return (0, 0, 0, 0)

        # Combine style padding and widget padding
        st_pad = style.configure(btn_style).get('padding', '')
        pad_widget = _parse_pad(btn_padding)
        pad_style = _parse_pad(st_pad)
        total_vpad = pad_widget[1] + pad_widget[3] + pad_style[1] + pad_style[3]
        print(f"style padding: {st_pad!r} -> parsed vpad={pad_style[1]}+{pad_style[3]}")
        print(f"computed total vertical padding (widget+style): {total_vpad}")
        need = metrics.get('linespace', 0) + total_vpad
        print(f"required internal height (linespace + vpad): {need}")
        print(f"height delta (widget_h - required): {bbox[1] - need}")
    except Exception as e:
        print("error computing padding/need:", e)

    # Done
    root.destroy()
    return 0


if __name__ == '__main__':
    sys.exit(main())
