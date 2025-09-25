"""
Base classes and utilities for UI components
Shared functionality across all UI modules
"""

import os
import sys
import unicodedata
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Dict, Any, Optional
from .ui_config import UIConfig, get_font, get_color, get_dimension
from utils.logger import logger


def open_folder_in_explorer(folder_path: str):
    """
    Open folder in file explorer (cross-platform)
    
    Args:
        folder_path: Path to folder to open
    """
    try:
        if os.name == 'nt':  # Windows
            os.startfile(folder_path)
        elif os.name == 'posix':  # macOS and Linux
            if sys.platform == 'darwin':  # macOS
                os.system(f'open "{folder_path}"')
            else:  # Linux
                os.system(f'xdg-open "{folder_path}"')
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open folder: {e}")


class BaseUIComponent:
    """Base class for UI components with common functionality"""

    _style_configured = False

    def __init__(self, parent, config_manager=None, api_client=None):
        self.parent = parent

        self._scrollables = []
        self.config = config_manager
        self.api_client = api_client
        self.widgets = {}
        self._themable_text_widgets = []
        self._themable_listboxes = []
        
        # Load UI configuration
        self.ui_config = UIConfig()
        self.FONTS = self.ui_config.FONTS
        self.COLORS = self.ui_config.COLORS  
        self.DIMENSIONS = self.ui_config.DIMENSIONS
        self.log = logger

        # Shared spacing metrics
        self.content_pad_x = self.DIMENSIONS.get('content_pad_x', 12)
        self.content_pad_y = self.DIMENSIONS.get('content_pad_y', 10)
        self.section_pad_y = self.DIMENSIONS.get('section_pad_y', 10)
        self.section_internal_pad = self.DIMENSIONS.get('section_internal_pad', 12)

        default_root = getattr(tk, '_default_root', None)
        if default_root is not None and not BaseUIComponent._style_configured:
            self._configure_styles()
            BaseUIComponent._style_configured = True


    def _configure_styles(self):
        """Configure ttk styles for a modern look"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        colors = self.COLORS
        fonts = self.FONTS

        background = colors.get('surface_bg', '#ffffff')
        window_bg = colors.get('window_bg', background)
        border = colors.get('border', '#d0d5dd')
        accent = colors.get('accent', '#2563eb')
        accent_hover = colors.get('accent_hover', '#1d4ed8')
        accent_active = colors.get('accent_active', '#1e40af')
        surface_hover = colors.get('surface_hover', '#e2e8f0')
        surface_active = colors.get('surface_active', '#cbd5f5')
        secondary = colors.get('text_secondary', '#475467')
        primary = colors.get('text_primary', '#111827')

        style.configure('.', font=fonts['label_normal'], background=background, foreground=primary)
        style.configure('TFrame', background=background)
        style.configure('Content.TFrame', background=background)
        style.configure('App.TFrame', background=window_bg)
        style.configure('TLabel', background=background, foreground=primary, font=fonts['label_normal'])
        style.configure('Header.TLabel', background=background, foreground=primary, font=fonts['label_bold'])
        style.configure('Subheader.TLabel', background=background, foreground=secondary, font=fonts['label_small'])

        tab_pad = self.DIMENSIONS.get('notebook_tab_pad', (16, 8))
        style.configure('TNotebook', background=window_bg, borderwidth=0)
        style.configure('TNotebook.Tab', padding=tab_pad, font=fonts['label_bold'], foreground=secondary)
        style.map('TNotebook.Tab',
                  background=[('selected', background), ('!selected', window_bg)],
                  foreground=[('selected', primary), ('!selected', secondary)])

        style.configure('Card.TLabelframe', background=background, borderwidth=1, relief='solid', bordercolor=border)
        style.configure('Card.TLabelframe.Label', background=background, foreground=secondary, font=fonts['label_small'])

        # Keep default button padding conservative to avoid global layout shifts
        style.configure('TButton', background=colors.get('surface_alt_bg', '#f3f4f6'),
                        foreground=primary, padding=(12, 7), borderwidth=0)
        style.map('TButton',
                  background=[('active', surface_hover), ('pressed', surface_active), ('disabled', background)],
                  foreground=[('disabled', secondary)])

        style.configure('Accent.TButton', background=accent, foreground='#ffffff', padding=(14, 8), borderwidth=0)
        style.map('Accent.TButton',
                  background=[('active', accent_hover), ('pressed', accent_active)],
                  foreground=[('disabled', '#e5e7eb')])

        # Reserved: per-widget padding tweaks are set on the widget (see server tab)

        style.configure('TCheckbutton', background=background, foreground=primary, font=fonts['label_normal'])
        style.configure('TRadiobutton', background=background, foreground=primary, font=fonts['label_normal'])
        style.configure('TCombobox', fieldbackground=background, background=background, foreground=primary)
        style.map('TCombobox', fieldbackground=[('readonly', background)])

        entry_bg = colors.get('surface_alt_bg', background)
        style.configure('TEntry',
                        fieldbackground=entry_bg,
                        background=entry_bg,
                        foreground=primary,
                        bordercolor=border,
                        insertcolor=accent)
        style.map('TEntry',
                  foreground=[('disabled', secondary)],
                  fieldbackground=[('disabled', colors.get('surface_bg', background)), ('focus', entry_bg)])

        style.configure('Treeview', background=background, fieldbackground=background, foreground=primary, bordercolor=border)
        style.configure('Treeview.Heading', font=fonts['label_bold'], foreground=secondary, background=colors.get('surface_alt_bg', '#f3f4f6'))

        # Scrollbar styling (ttk) for theme consistency
        try:
            sb_trough = colors.get('surface_alt_bg', '#f3f4f6')
            sb_bg = colors.get('surface_bg', background)
            style.configure('TScrollbar', background=sb_bg, troughcolor=sb_trough, bordercolor=border)
            style.configure('Vertical.TScrollbar', background=sb_bg, troughcolor=sb_trough, bordercolor=border)
            style.configure('Horizontal.TScrollbar', background=sb_bg, troughcolor=sb_trough, bordercolor=border)
        except Exception:
            pass

    def apply_theme(self):
        """Refresh cached colors/fonts and restyle tracked widgets."""
        self.ui_config = UIConfig()
        self.FONTS = self.ui_config.FONTS
        self.COLORS = self.ui_config.COLORS
        self.DIMENSIONS = self.ui_config.DIMENSIONS
        self.content_pad_x = self.DIMENSIONS.get('content_pad_x', 12)
        self.content_pad_y = self.DIMENSIONS.get('content_pad_y', 10)
        self.section_pad_y = self.DIMENSIONS.get('section_pad_y', 10)
        self.section_internal_pad = self.DIMENSIONS.get('section_internal_pad', 12)

        alive = []
        for widget, variant in self._themable_text_widgets:
            try:
                if widget.winfo_exists():
                    self.style_text_widget(widget, variant=variant, register=False)
                    alive.append((widget, variant))
            except tk.TclError:
                continue
        self._themable_text_widgets = alive

        alive_listboxes = []
        for widget, variant in self._themable_listboxes:
            try:
                if widget.winfo_exists():
                    self.style_listbox(widget, variant=variant, register=False)
                    alive_listboxes.append((widget, variant))
            except tk.TclError:
                continue
        self._themable_listboxes = alive_listboxes

        scroll_manager = getattr(self, 'scroll_manager', None)
        if scroll_manager and hasattr(scroll_manager, 'apply_theme'):
            scroll_manager.apply_theme()

        self.on_theme_changed()

    def on_theme_changed(self):
        """Hook for subclasses to update custom widgets when theme changes."""
        return


    def ensure_styles(self):
        """Ensure ttk styles are configured once a Tk root exists"""
        if not BaseUIComponent._style_configured:
            self._configure_styles()
            BaseUIComponent._style_configured = True

    def log_info(self, message: str):
        """Log informational message via shared logger"""
        logger.info(message)

    def log_warning(self, message: str):
        """Log warning message via shared logger"""
        logger.warn(message)

    def log_error(self, message: str):
        """Log error message via shared logger"""
        logger.error(message)

    def _normalize_initialdir(self, initialdir):
        """Normalize initial directory inputs for file dialogs"""
        if not initialdir:
            return ''
        try:
            return os.fspath(initialdir)
        except TypeError:
            return str(initialdir)

    def ask_open_file(self, *, title: str, initialdir: str = '', filetypes=None):
        """Wrapper around filedialog.askopenfilename with logging"""
        try:
            return filedialog.askopenfilename(
                title=title,
                initialdir=self._normalize_initialdir(initialdir),
                filetypes=filetypes or [("All files", "*.*")]
            )
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to open file dialog: {exc}")
            self.log_error(f"Open file dialog failed: {exc}")
            return ''

    def ask_save_file(self, *, title: str, initialdir: str = '', defaultextension: str = '', filetypes=None):
        """Wrapper around filedialog.asksaveasfilename with logging"""
        try:
            return filedialog.asksaveasfilename(
                title=title,
                initialdir=self._normalize_initialdir(initialdir),
                defaultextension=defaultextension,
                filetypes=filetypes or [("All files", "*.*")]
            )
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to open save dialog: {exc}")
            self.log_error(f"Save file dialog failed: {exc}")
            return ''

    def ask_directory(self, *, title: str, initialdir: str = ''):
        """Wrapper around filedialog.askdirectory with logging"""
        try:
            return filedialog.askdirectory(
                title=title,
                initialdir=self._normalize_initialdir(initialdir)
            )
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to open directory dialog: {exc}")
            self.log_error(f"Directory dialog failed: {exc}")
            return ''

    def _sanitize_text(self, text: Any) -> Any:
        """Clean common Unicode artifacts and control chars from UI strings."""
        try:
            if isinstance(text, str):
                cleaned = text.replace("\uFFFD", "").replace("\ufffd", "")
                # Replace common bullet artifacts with simple dashes
                cleaned = cleaned.replace("ï¿½?ï¿½", "-")
                cleaned = cleaned.replace("ï¿½?\"", " - ")
                # Strip other non-printable control characters except tab/newline
                cleaned = "".join(ch for ch in cleaned if ch == "\n" or ch == "\t" or 32 <= ord(ch) <= 126)
                return cleaned
        except Exception:
            pass
        return text
    
    def create_section(self, parent, title: str, padding: int = None, **kwargs):
        """Create a consistently styled section frame"""
        padding = padding if padding is not None else self.section_internal_pad
        return ttk.LabelFrame(parent, text=title, padding=padding, style='Card.TLabelframe', **kwargs)

    def style_text_widget(self, widget, *, variant: str = 'surface', register: bool = True):
        """Apply modern styling to text-based widgets and track them for theme updates"""
        bg = self.COLORS.get('surface_alt_bg') if variant == 'surface' else self.COLORS.get('surface_bg')
        widget.configure(bg=bg, fg=self.COLORS.get('text_primary', '#111827'),
                         insertbackground=self.COLORS.get('accent', '#2563eb'), borderwidth=0, highlightthickness=0)

        if register:
            for existing, _variant in self._themable_text_widgets:
                if existing is widget:
                    return
            self._themable_text_widgets.append((widget, variant))

    def style_listbox(self, widget, *, variant: str = 'surface', register: bool = True):
        """Apply styling to listbox widgets and track them for theme updates"""
        bg = self.COLORS.get('surface_alt_bg') if variant == 'surface' else self.COLORS.get('surface_bg')
        fg = self.COLORS.get('text_primary', '#111827')
        select_bg = self.COLORS.get('accent', '#2563eb')
        select_fg = '#ffffff'
        border = self.COLORS.get('border', '#d0d5dd')
        widget.configure(bg=bg, fg=fg, selectbackground=select_bg, selectforeground=select_fg,
                         highlightbackground=border, highlightcolor=border, highlightthickness=1,
                         relief='flat', activestyle='none')

        if register:
            for existing, _variant in self._themable_listboxes:
                if existing is widget:
                    return
            self._themable_listboxes.append((widget, variant))

    def apply_card_padding(self, widget):
        """Helper to apply consistent external padding"""
        manager = widget.winfo_manager()
        if manager == 'pack':
            widget.pack_configure(padx=self.content_pad_x, pady=(self.section_pad_y, 0))
        elif manager == 'grid':
            widget.grid_configure(padx=self.content_pad_x, pady=(self.section_pad_y, 0))

    def apply_control_padding(self, widget):
        """Apply vertical padding for grouped controls"""
        if widget.winfo_manager() == 'pack':
            widget.pack_configure(pady=(0, self.DIMENSIONS.get('control_pad_y', 8)))

    def create_toggle_switch(self, parent, variable: tk.BooleanVar, command=None, switch_type="toggle"):
        """Create a toggle switch button with configurable display styles
        
        Args:
            parent: Parent widget
            variable: BooleanVar to control state
            command: Optional callback function
            switch_type: "toggle" (ON/OFF) or "boolean" (TRUE/FALSE)
        """
        # Configure text and colors based on switch type
        if switch_type == "boolean":
            true_text, false_text = "TRUE", "FALSE"
            true_color, false_color = get_color('boolean_true'), get_color('boolean_false')
            width_key = 'boolean_button_width'
            height_key = 'boolean_button_height'
        else:
            true_text, false_text = "ON", "OFF"
            true_color, false_color = get_color('toggle_on'), get_color('toggle_off')
            width_key = 'toggle_button_width'
            height_key = 'toggle_button_height'
        
        def update_button_text():
            """Update button text and color based on current state"""
            if variable.get():
                button.config(text=true_text, foreground="white", background=true_color)
            else:
                button.config(text=false_text, foreground="white", background=false_color)
        
        def toggle_command():
            """Handle toggle switch click"""
            variable.set(not variable.get())
            update_button_text()
            if command:
                command()
        
        # Create button with fixed width for consistency
        button = tk.Button(parent, text="", width=get_dimension(width_key), height=get_dimension(height_key), 
                          font=("Arial", 7, "bold"), relief="raised", bd=1,
                          command=toggle_command, cursor="hand2")
        
        # Set initial state
        update_button_text()
        
        # Store update function for external access
        button.update_visual = update_button_text
        
        # Monitor variable changes
        def on_variable_change(*args):
            update_button_text()
        variable.trace_add('write', on_variable_change)
        
        return button
    
    def create_boolean_toggle_switch(self, parent, variable: tk.BooleanVar, command=None):
        """Create a boolean toggle switch button that shows TRUE/FALSE states"""
        return self.create_toggle_switch(parent, variable, command, switch_type="boolean")
    
    def create_hover_tooltip(self, widget, text):
        """Create a simple hover tooltip for a widget"""
        def on_enter(event):
            # Clean up any existing tooltip first
            if hasattr(widget, '_tooltip'):
                try:
                    widget._tooltip.destroy()
                except (tk.TclError, AttributeError):
                    pass  # Tooltip was already destroyed or invalid
                try:
                    del widget._tooltip
                except AttributeError:
                    pass  # Attribute already removed
            
            # Create tooltip window
            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.configure(bg="lightyellow", bd=1, relief="solid")
            
            # Position tooltip with smart positioning to avoid screen edge clipping
            x = widget.winfo_rootx() + 25
            y = widget.winfo_rooty() + 25
            
            # Simple aggressive approach: if widget is in bottom half of screen, position above
            screen_height = widget.winfo_screenheight()
            widget_y = widget.winfo_rooty()
            
            if widget_y > screen_height * 0.6:  # If widget is in bottom 40% of screen
                y = widget.winfo_rooty() - 150  # Position well above widget
                
            tooltip.geometry(f"+{x}+{y}")
            
            # Add text (sanitize artifacts for readability)
            safe_text = self._sanitize_text(text)
            label = tk.Label(tooltip, text=safe_text, bg="lightyellow", fg="black",
                           font=("Arial", 9), justify="left", wraplength=400)
            label.pack()
            
            # Store reference so we can destroy it
            widget._tooltip = tooltip
        
        def on_leave(event):
            # Destroy tooltip safely
            if hasattr(widget, '_tooltip'):
                try:
                    widget._tooltip.destroy()
                except (tk.TclError, AttributeError):
                    pass  # Tooltip was already destroyed or invalid
                try:
                    del widget._tooltip
                except AttributeError:
                    pass  # Attribute already removed
        
        # Bind events
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

# Override sanitizer with a Unicode-normalizing version across the app
def _normalized_sanitize(self, text):
    try:
        if not isinstance(text, str):
            return text
        s = unicodedata.normalize('NFKC', text)
        s = s.replace("\uFFFD", "").replace("\ufffd", "")
        return "".join(
            ch for ch in s
            if (ch in "\n\t") or (unicodedata.category(ch)[0] != 'C')
        )
    except Exception:
        return text

# Apply monkey-patch so existing calls use the improved sanitizer
BaseUIComponent._sanitize_text = _normalized_sanitize
class ScrollableFrameManager:
    """Manages scrollable frames with mousewheel support"""
    
    def __init__(self, parent):
        self.parent = parent

        self._scrollables = []
        # Load mouse wheel configuration
        mouse_config = UIConfig.get_mouse_wheel_config()
        self.mouse_wheel_delta = mouse_config["delta"]
        self.scroll_units_per_wheel = mouse_config["scroll_units"]
    
    def create_scrollable_frame(self, parent):
        """Create a scrollable frame with mousewheel support"""
        # Create main frame
        main_frame = ttk.Frame(parent, style='Content.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create canvas and scrollbar
        canvas = tk.Canvas(main_frame, highlightthickness=0, bd=0, background=self.parent.COLORS.get('surface_bg'))
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style='Content.TFrame')
        
        # Configure scrolling
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack scrollbar and canvas
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Enable mousewheel scrolling
        self._enable_mousewheel_scrolling(canvas, scrollable_frame)
        
        # Handle canvas resizing
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', on_canvas_configure)
        
        self._scrollables.append((main_frame, canvas, scrollable_frame))
        return main_frame, canvas, scrollable_frame
    
    def apply_theme(self):
        """Refresh backgrounds of managed scrollable areas."""
        try:
            bg = self.parent.COLORS.get('surface_bg')
        except AttributeError:
            bg = '#ffffff'
        for _frame, canvas, _scrollable in self._scrollables:
            try:
                canvas.configure(background=bg)
            except tk.TclError:
                continue
    
    def _enable_mousewheel_scrolling(self, canvas, container_widget):
        """Enable mousewheel scrolling for canvas and all child widgets"""
        def scroll_handler(event):
            if event.delta:
                # Windows/macOS
                delta = -1 * (event.delta / self.mouse_wheel_delta)
            else:
                # Linux
                delta = -1 if event.num == 4 else 1
            canvas.yview_scroll(int(delta * self.scroll_units_per_wheel), "units")
        
        # Collect all widgets that should support scrolling
        widgets_to_bind = [canvas, container_widget]
        
        def bind_children(widget):
            try:
                for child in widget.winfo_children():
                    widgets_to_bind.append(child)
                    bind_children(child)
            except (AttributeError, tk.TclError):
                pass  # Some widgets may not support winfo_children or may be destroyed
        
        bind_children(container_widget)
        
        # Bind to all widgets
        for widget in widgets_to_bind:
            try:
                # Windows/macOS
                widget.bind("<MouseWheel>", scroll_handler)
                # Linux
                widget.bind("<Button-4>", scroll_handler)
                widget.bind("<Button-5>", scroll_handler)
            except (AttributeError, tk.TclError):
                pass  # Some widgets may not support binding or may be destroyed


class ThemedScrolledText(ttk.Frame):
    """A scrolled text widget using ttk.Scrollbar to honor themes.

    Exposes common tk.Text methods by proxy so callers can treat this like a Text.
    Access the underlying text via .text if needed.
    """

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, style='Content.TFrame')
        self.text = tk.Text(self, *args, **kwargs)
        self.vscroll = ttk.Scrollbar(self, orient='vertical')

        # Hook a custom yscroll handler to enable/disable (but keep showing) the scrollbar when not needed
        def _yscroll(first, last):
            try:
                self.vscroll.set(first, last)
                # If full content fits, disable the scrollbar (keep themed trough visible)
                if float(first) <= 0.0 and float(last) >= 1.0:
                    try:
                        self.vscroll.state(["disabled"])
                    except Exception:
                        pass
                else:
                    try:
                        self.vscroll.state(["!disabled"])
                    except Exception:
                        pass
            except Exception:
                pass

        self.text.configure(yscrollcommand=_yscroll)
        self.vscroll.configure(command=self.text.yview)

        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # Always show scrollbar; it will be disabled when not needed
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)

    # Proxy common Text API
    def insert(self, *args, **kwargs):
        return self.text.insert(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.text.delete(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self.text.get(*args, **kwargs)

    def config(self, *args, **kwargs):
        return self.text.config(*args, **kwargs)

    configure = config

    def see(self, *args, **kwargs):
        return self.text.see(*args, **kwargs)

    def bind(self, *args, **kwargs):
        return self.text.bind(*args, **kwargs)

    def focus_set(self):
        return self.text.focus_set()






