"""
Benchmark UI Module - Advanced Implementation
Handles HuggingFace-integrated benchmark dataset loading, navigation, and export
Adapted from reference implementation to current modular architecture
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from .base_components import ThemedScrolledText
import json
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from .base_components import BaseUIComponent, ScrollableFrameManager
from benchmarking.dataset_manager import BenchmarkDataset
from benchmarking.cache_manager import CacheManager


class BenchmarkUI(BaseUIComponent):
    """Advanced benchmark UI with HuggingFace integration"""
    
    def __init__(self, parent, config_manager, api_client, cache_manager=None):
        super().__init__(parent, config_manager, api_client)
        self.parent = parent
        
        # Initialize benchmark dataset manager with shared cache and progress callback
        if cache_manager is None:
            raise ValueError("cache_manager is required - no fallback allowed for clean architecture")
        self.dataset_manager = BenchmarkDataset(cache_manager, self._progress_callback)
        
        # UI components for advanced benchmark functionality
        self.conv_category_var = None
        self.conv_category_combo = None
        self.conv_subcategory_var = None
        self.conv_subcategory_combo = None
        self.conv_status_label = None
        self.conv_question_var = None
        self.conv_question_entry = None
        self.conv_prev_btn = None
        self.conv_next_btn = None
        self.conv_go_btn = None
        self.conv_total_label = None
        self.conv_question_text = None
        self.conv_ground_truth_text = None
        self.conv_filename_var = None
        self.conv_result_label = None
        
        # Progress bar for dataset loading
        self.progress_bar = None
        self.progress_label = None
        self.load_btn = None
        self.browse_btn = None
        
        # Category display mapping for user-friendly names
        self.category_display_map = {}
        
        # Scrollable frame manager
        self.scroll_manager = ScrollableFrameManager(self)
    
    def _progress_callback(self, message: str, percent: int = None):
        """Progress callback for dataset loading"""
        if self.progress_label:
            self.progress_label.config(text=message)
        
        if self.progress_bar and percent is not None:
            self.progress_bar['value'] = percent
        
        # Update UI
        if hasattr(self.parent, 'root') and self.parent.root:
            self.parent.root.update()
    
    def create_benchmark_conversion_tab(self, notebook):
        """Create the advanced benchmark conversion tab"""
        conv_tab = ttk.Frame(notebook, style='Content.TFrame')
        notebook.add(conv_tab, text="Dataset Conversion")

        main_frame, _, scrollable = self.scroll_manager.create_scrollable_frame(conv_tab)
        # Reduce top padding to pull content closer to the notebook tabs
        main_frame.pack_configure(padx=self.content_pad_x, pady=(0, self.content_pad_y // 2))
        container = scrollable

        # Dataset Selection Section
        # Tighter internal padding to save vertical space (content unchanged)
        dataset_section = self.create_section(container, "Dataset Selection & Navigation", padding=8)
        # Minimal external padding for the first section to avoid top dead space
        dataset_section.pack(fill=tk.X, pady=(self.section_pad_y // 6, 0))
        # Apply consistent left/right margins so all sections share the same visual width
        self.apply_card_padding(dataset_section)

        select_frame = ttk.Frame(dataset_section, style='Content.TFrame')
        select_frame.pack(fill=tk.X, pady=(0, 2))

        ttk.Label(select_frame, text="Category:", font=self.FONTS['label_bold']).pack(side=tk.LEFT, padx=(0, 5))

        available_categories = self.dataset_manager.get_available_categories()
        category_labels = []
        self.category_display_map = {}
        for cat in available_categories:
            display_label = cat.replace('_', ' ').title()
            category_labels.append(display_label)
            self.category_display_map[display_label] = cat
        if not category_labels:
            category_labels = ["(Click 'Load Dataset' to explore LiveBench)"]

        self.conv_category_var = tk.StringVar(value=category_labels[0])
        self.conv_category_combo = ttk.Combobox(select_frame, textvariable=self.conv_category_var,
                                                values=category_labels, state="readonly", width=30)
        self.conv_category_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.conv_category_combo.bind('<<ComboboxSelected>>', self.on_conv_category_changed)

        ttk.Label(select_frame, text="Subcategory:", font=self.FONTS['label_bold']).pack(side=tk.LEFT, padx=(10, 5))
        self.conv_subcategory_var = tk.StringVar(value="all")
        self.conv_subcategory_combo = ttk.Combobox(select_frame, textvariable=self.conv_subcategory_var,
                                                   values=["all"], state="readonly", width=20)
        self.conv_subcategory_combo.pack(side=tk.LEFT, padx=(0, 10))

        self.load_btn = ttk.Button(select_frame, text="Load Complete Dataset", command=self.load_complete_dataset)
        self.load_btn.pack(side=tk.LEFT, padx=(10, 0))
        self.browse_btn = ttk.Button(select_frame, text="Browse Questions", command=self.load_specific_dataset)
        self.browse_btn.pack(side=tk.LEFT, padx=(5, 0))

        status_frame = ttk.Frame(dataset_section, style='Content.TFrame')
        # Minimize vertical padding; progress bar will appear only during load
        status_frame.pack(fill=tk.X, pady=(0, 1))
        cache_info = self.dataset_manager.get_cache_info()
        if cache_info.get('exists', False):
            status_text = (f"Cached data available ({cache_info.get('total_categories', 0)} categories, "
                           f"{cache_info.get('total_subcategories', 0)} subcategories) - Click 'Browse Questions' to start exploring")
        else:
            status_text = "Step 1: Click 'Load Complete Dataset' to fetch categories from HuggingFace"
        self.conv_status_label = ttk.Label(status_frame, text=status_text,
                                           foreground=self.COLORS.get('text_secondary'))
        self.conv_status_label.pack(anchor='w')
        self.progress_label = ttk.Label(status_frame, text="", foreground=self.COLORS.get('blue_text'))
        self.progress_label.pack(anchor='w')
        self.progress_bar = ttk.Progressbar(status_frame, mode='determinate')
        # Do not pack here to avoid occupying space when idle

        # Navigation controls (consolidated into the same section)
        nav_controls = ttk.Frame(dataset_section, style='Content.TFrame')
        nav_controls.pack(fill=tk.X, pady=(0, 0))

        self.conv_prev_btn = ttk.Button(nav_controls, text="< Previous", command=self.conv_prev_question,
                                        state="disabled", width=12)
        self.conv_prev_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Label(nav_controls, text="Question:").pack(side=tk.LEFT, padx=(0, 5))
        self.conv_question_var = tk.StringVar()
        self.conv_question_entry = ttk.Entry(nav_controls, textvariable=self.conv_question_var,
                                             width=8, font=self.FONTS['code_normal'])
        self.conv_question_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.conv_question_entry.bind('<Return>', lambda e: self.conv_go_to_question())

        self.conv_next_btn = ttk.Button(nav_controls, text="Next >", command=self.conv_next_question,
                                        state="disabled", width=12)
        self.conv_next_btn.pack(side=tk.LEFT, padx=(5, 10))

        self.conv_total_label = ttk.Label(nav_controls, text="(0 total)",
                                          font=self.FONTS['label_normal'],
                                          foreground=self.COLORS.get('text_secondary'))
        self.conv_total_label.pack(side=tk.LEFT, padx=(0, 10))

        self.conv_go_btn = ttk.Button(nav_controls, text="Go", command=self.conv_go_to_question,
                                      state="disabled")
        self.conv_go_btn.pack(side=tk.RIGHT)

        # Preview Section with controlled height (slightly shorter than default)
        preview_section = self.create_section(container, "Question Preview")
        # Slightly reduce gap above preview to save a few pixels
        preview_section.pack(fill=tk.X, expand=False, pady=(self.section_pad_y // 6, 0))
        self.apply_card_padding(preview_section)
        preview_section.columnconfigure(0, weight=1)

        pane = ttk.Panedwindow(preview_section, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.X, expand=False)

        question_card = ttk.Frame(pane, style='Content.TFrame')
        pane.add(question_card, weight=3)
        q_hdr = ttk.Frame(question_card, style='Content.TFrame')
        q_hdr.pack(fill=tk.X)
        ttk.Label(q_hdr, text="Question", font=self.FONTS['label_bold']).pack(side=tk.LEFT, anchor='w')
        ttk.Button(q_hdr, text="View Full", command=self._view_full_question).pack(side=tk.RIGHT)
        # Slightly taller than prior attempt: ~80% of JSON_PREVIEW_HEIGHT, with a minimum
        _preview_lines = max(8, int(self.ui_config.JSON_PREVIEW_HEIGHT * 0.8))
        self.conv_question_text = ThemedScrolledText(question_card,
                                                     font=self.FONTS['code_normal'], wrap=tk.WORD,
                                                     height=_preview_lines)
        self.conv_question_text.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        self.style_text_widget(self.conv_question_text.text)
        self.conv_question_text.insert(tk.END, "1. Load Complete Dataset\n2. Select category/subcategory\n3. Click 'Browse Questions' to view questions")
        self.conv_question_text.config(state=tk.DISABLED)

        answer_card = ttk.Frame(pane, style='Content.TFrame')
        pane.add(answer_card, weight=2)
        a_hdr = ttk.Frame(answer_card, style='Content.TFrame')
        a_hdr.pack(fill=tk.X)
        ttk.Label(a_hdr, text="Ground Truth", font=self.FONTS['label_bold']).pack(side=tk.LEFT, anchor='w')
        ttk.Button(a_hdr, text="View Full", command=self._view_full_ground_truth).pack(side=tk.RIGHT)
        self.conv_ground_truth_text = ThemedScrolledText(answer_card,
                                                         font=self.FONTS['code_normal'], wrap=tk.WORD,
                                                         height=_preview_lines)
        self.conv_ground_truth_text.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        self.style_text_widget(self.conv_ground_truth_text.text)
        self.conv_ground_truth_text.insert(tk.END, "Ground truth answers will appear here after loading questions...")
        self.conv_ground_truth_text.config(state=tk.DISABLED)

        # Export Section
        export_section = self.create_section(container, "Text Export")
        export_section.pack(fill=tk.X, pady=(self.section_pad_y // 6, 0))
        self.apply_card_padding(export_section)

        conv_controls = ttk.Frame(export_section, style='Content.TFrame')
        conv_controls.pack(fill=tk.X, pady=(0, 4))

        export_btn = ttk.Button(conv_controls, text="Export to Text",
                                 command=self.export_dataset_to_text, style='Accent.TButton')
        export_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(conv_controls, text="Filename (optional):").pack(side=tk.LEFT, padx=(0, 5))
        self.conv_filename_var = tk.StringVar()
        filename_entry = ttk.Entry(conv_controls, textvariable=self.conv_filename_var, width=30)
        filename_entry.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(conv_controls, text="Questions:").pack(side=tk.LEFT, padx=(0, 5))
        self.conv_export_range_var = tk.StringVar(value="all")
        range_entry = ttk.Entry(conv_controls, textvariable=self.conv_export_range_var, width=16)
        range_entry.pack(side=tk.LEFT)
        self.create_hover_tooltip(range_entry, "Export range: all, 1, 1-10, 1,3,5-8")

        view_files_btn = ttk.Button(conv_controls, text="View Exported Files",
                                     command=self.view_exported_files)
        view_files_btn.pack(side=tk.RIGHT)

        self.conv_result_label = ttk.Label(export_section,
                                           text="Load a dataset and click Export to Text",
                                           foreground=self.COLORS.get('text_secondary'))
        self.conv_result_label.pack(anchor='w', pady=(self.section_internal_pad // 2, 0))

        if hasattr(self, 'conv_category_var') and self.conv_category_var and self.conv_category_var.get():
            self.on_conv_category_changed()

    def _view_full_question(self):
        try:
            content = self.conv_question_text.get('1.0', tk.END)
        except Exception:
            content = ""
        self._show_full_text_dialog("Full Question", content)

    def _view_full_ground_truth(self):
        try:
            content = self.conv_ground_truth_text.get('1.0', tk.END)
        except Exception:
            content = ""
        self._show_full_text_dialog("Full Ground Truth", content)

    def _show_full_text_dialog(self, title: str, content: str):
        try:
            dlg = tk.Toplevel(self.parent.root)
            dlg.title(title)
            dlg.geometry("800x600")
            frm = ttk.Frame(dlg, style='Content.TFrame')
            frm.pack(fill=tk.BOTH, expand=True, padx=self.content_pad_x, pady=self.content_pad_y)
            bar = ttk.Frame(frm, style='Content.TFrame')
            bar.pack(fill=tk.X)
            ttk.Label(bar, text=title, font=self.FONTS['label_bold']).pack(side=tk.LEFT)
            def _copy():
                try:
                    dlg.clipboard_clear()
                    dlg.clipboard_append(content)
                except Exception:
                    pass
            ttk.Button(bar, text="Copy", command=_copy).pack(side=tk.RIGHT)
            txt = scrolledtext.ScrolledText(frm, font=self.FONTS['code_normal'], wrap=tk.WORD)
            self.style_text_widget(txt)
            txt.pack(fill=tk.BOTH, expand=True, pady=(4,0))
            try:
                # Preserve text exactly as displayed in the preview panes
                txt.insert('1.0', content)
                txt.config(state=tk.DISABLED)
            except Exception:
                pass
        except Exception:
            pass

    def on_conv_category_changed(self, event=None):
        """Handle category selection change"""
        try:
            display_category = self.conv_category_var.get()
            actual_category = self.category_display_map.get(display_category, display_category)
            
            # Get subcategories from cache
            subcategories = self.dataset_manager.get_subcategories(actual_category)
            
            if subcategories:
                # We have cached subcategories
                if "all" not in subcategories:
                    subcategories = ["all"] + subcategories
                self.conv_subcategory_combo['values'] = subcategories
                self.conv_subcategory_var.set("all")
            else:
                # No cached subcategories available
                self.conv_subcategory_combo['values'] = ["all", "(Load complete dataset to see more)"]
                self.conv_subcategory_var.set("all")
            
        except Exception as e:
            self.conv_status_label.config(text=f"Error: {e}", foreground="red")
    
    def load_complete_dataset(self):
        """Load complete LiveBench dataset and build cache"""
        try:
            # Show progress bar
            self.progress_bar.pack(fill=tk.X, pady=(5, 0))
            self.progress_bar['value'] = 0
            
            # Disable load button during loading
            if self.load_btn:
                self.load_btn.config(state='disabled')
            
            self.conv_status_label.config(text="Loading complete LiveBench dataset...", foreground="blue")
            self.parent.root.update()
            
            # Load complete dataset metadata
            success = self.dataset_manager.load_complete_dataset_cache()
            
            if success:
                # Hide progress bar
                self.progress_bar.pack_forget()
                self.progress_label.config(text="")
                
                # Update category dropdown with newly loaded categories
                self._refresh_category_dropdown()
                
                # Update status
                cache_info = self.dataset_manager.get_cache_info()
                status_text = f"Successfully loaded {cache_info.get('total_categories', 0)} categories with {cache_info.get('total_subcategories', 0)} subcategories - Step 2: Select category/subcategory and click 'Browse Questions'"
                self.conv_status_label.config(text=status_text, foreground="green")
                
            else:
                self.progress_bar.pack_forget()
                self.conv_status_label.config(text="Failed to load dataset - check console for details", foreground="red")
                
        except Exception as e:
            self.progress_bar.pack_forget()
            self.conv_status_label.config(text=f"Error: {e}", foreground="red")
        
        finally:
            # Re-enable load button
            if self.load_btn:
                self.load_btn.config(state='normal')
    
    def _refresh_category_dropdown(self):
        """Refresh category dropdown with newly cached data"""
        try:
            # Get updated categories from cache
            available_categories = self.dataset_manager.get_available_categories()
            category_labels = []
            self.category_display_map = {}
            
            # Create user-friendly display names
            for cat in available_categories:
                display_label = cat.replace('_', ' ').title()
                category_labels.append(display_label)
                self.category_display_map[display_label] = cat
            
            # Update category combo values using direct reference
            if self.conv_category_combo and category_labels:
                self.conv_category_combo['values'] = category_labels
                self.conv_category_combo.set(category_labels[0])
                
                # Also update the subcategory dropdown for the first category
                if category_labels:
                    first_category = self.category_display_map[category_labels[0]]
                    subcategories = self.dataset_manager.get_subcategories(first_category)
                    if subcategories:
                        if "all" not in subcategories:
                            subcategories = ["all"] + subcategories
                        self.conv_subcategory_combo['values'] = subcategories
                        self.conv_subcategory_combo.set("all")
                
                self.log_info(f"Updated category dropdown with {len(category_labels)} categories")
                        
        except Exception as e:
            self.log_error(f"Error refreshing category dropdown: {e}")
    
    def load_specific_dataset(self):
        """Load specific category dataset for browsing questions"""
        try:
            display_category = self.conv_category_var.get()
            actual_category = self.category_display_map.get(display_category, display_category)
            subcategory = self.conv_subcategory_var.get()
            
            # Validate selections
            if not actual_category or actual_category.startswith("(Click"):
                self.conv_status_label.config(text="Please select a category first", foreground="red")
                return
                
            if not subcategory:
                subcategory = "all"
            
            # Disable browse button during loading
            if self.browse_btn:
                self.browse_btn.config(state='disabled')
            
            self.conv_status_label.config(text=f"Loading {actual_category} ({subcategory}) questions...", foreground="blue")
            self.parent.root.update()
            
            # Load specific dataset for browsing
            success = self.dataset_manager.load_dataset(actual_category, subcategory)
            
            if success:
                nav_info = self.dataset_manager.get_navigation_info()
                self.conv_status_label.config(
                    text=f"Loaded {nav_info['total_questions']} questions from {actual_category} ({subcategory})", 
                    foreground="green"
                )
                
                # Enable navigation controls
                self.conv_prev_btn.config(state="normal")
                self.conv_next_btn.config(state="normal")
                self.conv_go_btn.config(state="normal")
                self.conv_question_entry.config(state="normal")
                
                # Update total label
                self.conv_total_label.config(text=f"({nav_info['total_questions']} total)")
                
                # Display first question
                self.update_conversion_display()
                
            else:
                self.conv_status_label.config(text="Failed to load questions - check console for details", foreground="red")
                # Disable navigation controls
                self.conv_prev_btn.config(state="disabled")
                self.conv_next_btn.config(state="disabled")
                self.conv_go_btn.config(state="disabled")
                self.conv_question_entry.config(state="disabled")
                
        except Exception as e:
            self.conv_status_label.config(text=f"Error: {e}", foreground="red")
        
        finally:
            # Re-enable browse button
            if self.browse_btn:
                self.browse_btn.config(state='normal')
    
    def update_conversion_display(self):
        """Update question and ground truth display"""
        try:
            question_text, ground_truth = self.dataset_manager.get_current_question_display()
            nav_info = self.dataset_manager.get_navigation_info()
            
            # Update question display
            self.conv_question_text.config(state=tk.NORMAL)
            self.conv_question_text.delete("1.0", tk.END)
            self.conv_question_text.insert("1.0", question_text)
            self.conv_question_text.config(state=tk.DISABLED)
            
            # Update ground truth display
            self.conv_ground_truth_text.config(state=tk.NORMAL)
            self.conv_ground_truth_text.delete("1.0", tk.END)
            self.conv_ground_truth_text.insert("1.0", ground_truth)
            self.conv_ground_truth_text.config(state=tk.DISABLED)
            
            # Update question number
            self.conv_question_var.set(str(nav_info['current_question']))
            
        except Exception as e:
            self.log_error(f"Error updating display: {e}")
    
    def conv_prev_question(self):
        """Navigate to previous question"""
        nav_info = self.dataset_manager.get_navigation_info()
        if nav_info['current_question'] > 1:
            self.dataset_manager.navigate_to_question(nav_info['current_question'] - 1)
            self.update_conversion_display()
    
    def conv_next_question(self):
        """Navigate to next question"""
        nav_info = self.dataset_manager.get_navigation_info()
        if nav_info['current_question'] < nav_info['total_questions']:
            self.dataset_manager.navigate_to_question(nav_info['current_question'] + 1)
            self.update_conversion_display()
    
    def conv_go_to_question(self):
        """Navigate to specific question number"""
        try:
            question_num = int(self.conv_question_var.get())
            if self.dataset_manager.navigate_to_question(question_num):
                self.update_conversion_display()
            else:
                nav_info = self.dataset_manager.get_navigation_info()
                messagebox.showerror("Invalid Question", 
                                   f"Question number must be between 1 and {nav_info['total_questions']}")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid question number")
    
    def export_dataset_to_text(self):
        """Export current dataset to text format"""
        try:
            if not self.dataset_manager.current_dataset:
                messagebox.showwarning("No Dataset", "Please load a dataset first")
                return
            
            # Get filename from user input
            filename = self.conv_filename_var.get().strip()
            
            self.conv_result_label.config(text="Exporting to text...", foreground="blue")
            self.parent.root.update()
            
            # Export to text with optional question range
            question_range = self.conv_export_range_var.get().strip() if hasattr(self, 'conv_export_range_var') else 'all'
            output_path, exported_count = self.dataset_manager.export_to_text(filename if filename else None, question_range)
            
            # Show success message
            nav_info = self.dataset_manager.get_navigation_info()
            result_text = f"Successfully exported {exported_count} questions to {os.path.basename(output_path)}"
            self.conv_result_label.config(text=result_text, foreground="green")
            
            # Show success dialog with option to open folder
            result = messagebox.askquestion("Export Complete", 
                                          f"{result_text}\n\nWould you like to open the exports folder?")
            if result == 'yes':
                self._open_folder(self.dataset_manager.output_dir)
                
        except Exception as e:
            error_msg = f"Export failed: {e}"
            self.conv_result_label.config(text=error_msg, foreground="red")
            messagebox.showerror("Export Error", error_msg)
    
    def view_exported_files(self):
        """Show list of exported files"""
        files = self.dataset_manager.get_exported_files()
        
        if not files:
            messagebox.showinfo("No Files", "No exported text files found")
            return
        
        # Create a dialog to show files
        dialog = tk.Toplevel(self.parent.root)
        dialog.title("Exported Text Files")
        dialog.geometry("600x400")
        
        ttk.Label(dialog, text="Previously Converted Files:", font=self.FONTS['label_bold']).pack(pady=10)
        
        # File list
        file_frame = ttk.Frame(dialog)
        file_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        file_listbox = tk.Listbox(file_frame, font=self.FONTS['code_normal'])
        file_listbox.pack(fill=tk.BOTH, expand=True)
        self.style_listbox(file_listbox)
        
        for file in files:
            file_listbox.insert(tk.END, file)
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(btn_frame, text="Open Folder", 
                   command=lambda: self._open_folder(self.dataset_manager.output_dir)).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)
    
    def _open_folder(self, folder_path: str):
        """Open folder in file explorer (cross-platform)"""
        from .base_components import open_folder_in_explorer
        open_folder_in_explorer(folder_path)
    
    def set_scroll_sensitivity(self, sensitivity: int):
        """Update scroll sensitivity for scrollable components"""
        # Update scroll manager if needed
        if hasattr(self.scroll_manager, 'scroll_units_per_wheel'):
            self.scroll_manager.scroll_units_per_wheel = sensitivity

