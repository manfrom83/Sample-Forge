"""
Scoring UI and Algorithms Module
Provides interface for scoring benchmark runs and displays results
Supports EXACT and PARTIAL scoring modes with transparent display
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import json
import re
import csv
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from .base_components import BaseUIComponent, ThemedScrolledText

# Flexible scoring system - all category-specific functions removed
# Using single flexible_scorer.py for all scoring needs

class ScoringVisualizer:
    """ASCII visualization for scoring results"""
    
    @staticmethod
    def create_progress_bar(percentage: float, width: int = 40) -> str:
        """Create ASCII progress bar"""
        filled = int(width * percentage / 100)
        empty = width - filled
        return f"[{'=' * filled}{' ' * empty}]"
    
    @staticmethod
    def create_result_bar(correct: int, total: int, width: int = 40) -> str:
        """Create result visualization bar"""
        if total == 0:
            return "[" + " " * width + "]"
        
        correct_width = int(width * correct / total)
        incorrect_width = width - correct_width
        
        return f"[{'+'*correct_width}{'-'*incorrect_width}]"

class ScoringUI(BaseUIComponent):
    """UI for scoring benchmark results"""
    
    def __init__(self, parent, config_manager, api_client):
        super().__init__(parent, config_manager, api_client)
        self.parent = parent
        
        # Scoring state
        self.selected_run = None
        self.scoring_results = None
        
        # UI components
        self.run_listbox = None
        self.refresh_btn = None
        self.score_btn = None
        self.results_text = None
        self.export_csv_btn = None
        self.export_summary_btn = None
        self.open_folder_btn = None
        
        # Use centralized path management for benchmark runs
        from managers.path_manager import app_paths
        from managers.global_settings import global_settings
        # Allow overriding the runs directory via global settings
        custom_runs = global_settings.get_runs_dir()
        self.runs_dir = custom_runs if (custom_runs and os.path.isdir(custom_runs)) else str(app_paths.benchmark_runs)
        os.makedirs(self.runs_dir, exist_ok=True)
    

    def create_scoring_tab(self, notebook):
        """Create the Scoring & Analysis tab"""
        scoring_tab = ttk.Frame(notebook, style='Content.TFrame')
        notebook.add(scoring_tab, text="Scoring & Analysis")

        content = ttk.Frame(scoring_tab, style='Content.TFrame')
        content.pack(fill=tk.BOTH, expand=True, padx=self.content_pad_x, pady=self.content_pad_y)

        # ----- Run selection -----
        selection_section = self.create_section(content, "Select Benchmark Run")
        selection_section.pack(fill=tk.X)
        self.apply_card_padding(selection_section)
        selection_section.columnconfigure(0, weight=1)

        ttk.Label(selection_section, text="Available Runs:", font=self.FONTS['label_bold']).grid(row=0, column=0, sticky='w')

        listbox_frame = ttk.Frame(selection_section, style='Content.TFrame')
        listbox_frame.grid(row=1, column=0, sticky='ew', pady=(6, 10))
        listbox_frame.columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(listbox_frame, orient='vertical')
        scrollbar.grid(row=0, column=1, sticky='ns')

        self.run_listbox = tk.Listbox(
            listbox_frame,
            height=9,
            yscrollcommand=scrollbar.set,
            font=self.FONTS['code_normal']
        )
        self.run_listbox.grid(row=0, column=0, sticky='nsew')
        self.style_listbox(self.run_listbox)
        scrollbar.config(command=self.run_listbox.yview)
        self.run_listbox.bind('<<ListboxSelect>>', self.on_run_selected)

        mode_frame = ttk.Frame(selection_section, style='Content.TFrame')
        mode_frame.grid(row=2, column=0, sticky='w', pady=(0, 6))
        ttk.Label(mode_frame, text="Scoring Mode:", font=self.FONTS['label_bold']).pack(side=tk.LEFT)

        self.scoring_mode_var = tk.StringVar(value="EXACT")
        for text_label, value in (("Exact Match", "EXACT"), ("Partial Credit", "PARTIAL")):
            ttk.Radiobutton(mode_frame, text=text_label, variable=self.scoring_mode_var, value=value).pack(side=tk.LEFT, padx=(10, 0))

        btn_frame = ttk.Frame(selection_section, style='Content.TFrame')
        btn_frame.grid(row=3, column=0, sticky='w')
        self.refresh_btn = ttk.Button(btn_frame, text="Refresh List", command=self.refresh_run_list)
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.score_btn = ttk.Button(btn_frame, text="Score Selected Run", command=self.score_selected_run, state='disabled')
        self.score_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.change_dir_btn = ttk.Button(btn_frame, text="Change Runs Folder", command=self.change_runs_folder)
        self.change_dir_btn.pack(side=tk.LEFT)

        # ----- Results -----
        results_section = self.create_section(content, "Scoring Results")
        results_section.pack(fill=tk.BOTH, expand=True, pady=(self.section_pad_y, 0))
        self.apply_card_padding(results_section)
        results_section.columnconfigure(0, weight=1)
        results_section.rowconfigure(0, weight=1)

        self.results_text = ThemedScrolledText(
            results_section,
            height=16,
            font=self.FONTS['code_normal']
        )
        self.style_text_widget(self.results_text.text)
        self.results_text.grid(row=0, column=0, sticky='nsew')

        # ----- Export controls -----
        export_section = self.create_section(content, "Export Results")
        export_section.pack(fill=tk.X, pady=(self.section_pad_y, 0))
        self.apply_card_padding(export_section)

        export_btn_frame = ttk.Frame(export_section, style='Content.TFrame')
        export_btn_frame.pack(anchor='w')

        self.export_csv_btn = ttk.Button(export_btn_frame, text="Export to CSV", command=self.export_to_csv, state='disabled')
        self.export_csv_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.export_summary_btn = ttk.Button(export_btn_frame, text="Export Summary Report", command=self.export_summary_report, state='disabled')
        self.export_summary_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.open_folder_btn = ttk.Button(export_btn_frame, text="Open Folder", command=self.open_results_folder, state='disabled')
        self.open_folder_btn.pack(side=tk.LEFT)

        # Initial population
        self.refresh_run_list()

    def refresh_runs_if_needed(self):
        """Refresh runs list if needed (called automatically after benchmark completion)"""
        self.refresh_run_list()
    
    def refresh_run_list(self):
        """Refresh the list of available benchmark runs"""
        self.run_listbox.delete(0, tk.END)
        
        if not os.path.exists(self.runs_dir):
            return
            
        # Find all run directories
        runs = []
        for item in os.listdir(self.runs_dir):
            run_path = os.path.join(self.runs_dir, item)
            if os.path.isdir(run_path):
                # Check if it has required files (unified structure only needs metadata.json)
                metadata_path = os.path.join(run_path, 'metadata.json')
                
                if os.path.exists(metadata_path):
                    # Read metadata to get status
                    try:
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                        
                        run_info = metadata.get('run_info', {})
                        status = run_info.get('status', 'unknown')
                        total_questions = run_info.get('total_selected', 0)
                        
                        display_text = f"{item} ({status}) - {total_questions} questions"
                        runs.append((item, display_text))
                        
                    except Exception:
                        runs.append((item, f"{item} (error reading metadata)"))
        
        # Sort by name (newest first)
        runs.sort(reverse=True)
        
        # Add to listbox
        for run_name, display_text in runs:
            self.run_listbox.insert(tk.END, display_text)
        
        if runs:
            self.run_listbox.selection_set(0)
            self.on_run_selected()

    def change_runs_folder(self):
        """Let user choose a different runs directory (for scoring runs created elsewhere)."""
        from tkinter import filedialog
        initial = self.runs_dir if os.path.isdir(self.runs_dir) else os.getcwd()
        new_dir = filedialog.askdirectory(title="Select Benchmark Runs Folder", initialdir=initial)
        if not new_dir:
            return
        # Persist and refresh
        try:
            from managers.global_settings import global_settings
            self.runs_dir = new_dir
            global_settings.set_runs_dir(new_dir)
            self.refresh_run_list()
            self.log_info(f"Runs folder set to: {new_dir}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to set runs folder: {e}")
    
    def on_run_selected(self, event=None):
        """Handle run selection"""
        selection = self.run_listbox.curselection()
        if selection:
            # Extract run name from display text
            display_text = self.run_listbox.get(selection[0])
            self.selected_run = display_text.split(' ')[0]
            self.score_btn.config(state='normal')
        else:
            self.selected_run = None
            self.score_btn.config(state='disabled')
    
    def score_selected_run(self):
        """Score the selected benchmark run"""
        if not self.selected_run:
            messagebox.showwarning("No Selection", "Please select a run to score")
            return
            
        try:
            # Clear previous results
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert("1.0", "Scoring in progress...\n")
            self.parent.root.update()
            
            # Score the run
            results = self.score_benchmark_run(self.selected_run)
            self.scoring_results = results
            
            # Display results
            self.display_scoring_results(results)
            
            # Enable export buttons
            self.export_csv_btn.config(state='normal')
            self.export_summary_btn.config(state='normal')
            self.open_folder_btn.config(state='normal')
            
        except Exception as e:
            messagebox.showerror("Scoring Error", f"Failed to score run: {str(e)}")
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert("1.0", f"Error: {str(e)}")
    
    def score_benchmark_run(self, run_name: str) -> Dict[str, Any]:
        """Score a benchmark run using LiveBench algorithms"""
        run_path = os.path.join(self.runs_dir, run_name)
        
        # Load unified metadata (single source of truth)
        meta_path = os.path.join(run_path, 'metadata.json')
        with open(meta_path, 'r') as f:
            metadata = json.load(f)
        
        # Extract questions from unified structure
        questions = metadata.get('questions', [])
        
        # Score each question
        results = {
            'run_name': run_name,
            'total_questions': len(questions),
            'scores': [],
            'category_scores': {},
            'task_scores': {},
            'overall_accuracy': 0.0,
            'run_metadata': metadata['run_info']  # Store run info, not raw responses
        }
        
        correct_count = 0
        
        for question in questions:
            # Determine scoring method based on task type
            task = question.get('task', 'unknown')
            category = question.get('category', 'unknown')
            ground_truth = question.get('ground_truth', '')
            llm_answer = question.get('response', '')
            
            # Use flexible scoring system - no hardcoded categories!
            from benchmarking.scorer import FlexibleScorer
            
            # Get scoring mode from UI selection
            scoring_mode = self.scoring_mode_var.get()
            
            # Score using flexible system
            scorer = FlexibleScorer()
            score = scorer.score_answer(ground_truth, llm_answer, scoring_mode)
            
            # Extract the answer that was actually used for scoring (single source of truth)
            extracted_answer = scorer.extract_answer(llm_answer)
            
            # Add mode to record for transparency
            question['scoring_mode_used'] = scoring_mode
            
            # Record score with both truncated context and extracted answer
            score_record = {
                'question_id': question.get('q_id'),
                'score': score,
                'task': task,
                'category': category,
                'ground_truth': ground_truth,
                'llm_answer': llm_answer[:200] + '...' if len(llm_answer) > 200 else llm_answer,
                'extracted_answer': extracted_answer  # Store what was actually scored
            }
            results['scores'].append(score_record)
            
            # Update counts
            if score >= 1.0:
                correct_count += 1
            elif score >= 0.5:
                correct_count += 0.5
            
            # Update category scores
            if category not in results['category_scores']:
                results['category_scores'][category] = {'total': 0, 'correct': 0}
            results['category_scores'][category]['total'] += 1
            results['category_scores'][category]['correct'] += score
            
            # Update task scores
            if task not in results['task_scores']:
                results['task_scores'][task] = {'total': 0, 'correct': 0}
            results['task_scores'][task]['total'] += 1
            results['task_scores'][task]['correct'] += score
        
        # Calculate overall accuracy
        if results['total_questions'] > 0:
            results['overall_accuracy'] = (correct_count / results['total_questions']) * 100
        
        # Save scoring results as simple text format matching UI display
        scoring_dir = os.path.join(run_path, 'scoring')
        os.makedirs(scoring_dir, exist_ok=True)
        
        # Generate text output in EXACT mode format (always use EXACT for saved file)
        correct_count = sum(1 for s in results['scores'] if s['score'] >= 1.0)
        text_output = f"Benchmark Run: {results['run_name']}\n"
        text_output += f"Correct: {correct_count}/{results['total_questions']}\n\n"
        
        # Display each question in simple EXACT format
        for score_record in results['scores']:
            q_id = score_record.get('question_id', 0)
            is_correct = score_record['score'] >= 1.0
            result_indicator = "V" if is_correct else "X"
            extracted_answer = score_record.get('extracted_answer', 'N/A')
            
            text_output += f"{q_id:03d}. [O] Ground truth: {score_record['ground_truth']}\n"
            text_output += f"{q_id:03d}. [{result_indicator}] LLM response: {extracted_answer}\n\n"
        
        with open(os.path.join(scoring_dir, 'scoring_results.txt'), 'w', encoding='utf-8') as f:
            f.write(text_output)
        
        return results
    
    def display_scoring_results(self, results: Dict[str, Any]):
        """Display scoring results in format based on scoring mode"""
        self.results_text.delete("1.0", tk.END)
        
        # Get current scoring mode to determine display format
        scoring_mode = getattr(self, 'scoring_mode_var', None)
        is_partial_mode = scoring_mode and scoring_mode.get() == "PARTIAL"
        
        if is_partial_mode:
            # PARTIAL mode: Show total score and decimal scores
            total_score = sum(s['score'] for s in results['scores'])
            output = f"Total Score: {total_score:.1f}/{results['total_questions']}\n\n"
            
            # Display each question with decimal scores
            for score_record in results['scores']:
                q_id = score_record.get('question_id', 0)
                extracted_answer = score_record.get('extracted_answer', 'N/A')
                score = score_record['score']
                
                # Simple format with zero-padded question numbers for perfect alignment
                output += f"{q_id:03d}. [OOOO] Ground truth: {score_record['ground_truth']}\n"
                output += f"{q_id:03d}. [{score:.2f}] LLM response: {extracted_answer}\n\n"
        else:
            # EXACT mode: Show correct count and checkmarks/X
            correct_count = sum(1 for s in results['scores'] if s['score'] >= 1.0)
            output = f"Correct: {correct_count}/{results['total_questions']}\n\n"
            
            # Display each question with V/X indicators
            for score_record in results['scores']:
                q_id = score_record.get('question_id', 0)
                is_correct = score_record['score'] >= 1.0
                result_indicator = "V" if is_correct else "X"
                extracted_answer = score_record.get('extracted_answer', 'N/A')
                
                # Simple format with zero-padded question numbers for perfect alignment
                output += f"{q_id:03d}. [O] Ground truth: {score_record['ground_truth']}\n"
                output += f"{q_id:03d}. [{result_indicator}] LLM response: {extracted_answer}\n\n"
        
        self.results_text.insert("1.0", output)
        self.results_text.see("1.0")
    
    def export_to_csv(self):
        """Export scoring results to CSV"""
        if not self.scoring_results:
            return
            
        # Ask for save location
        filename = self.ask_save_file(
            title="Export Results to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{self.selected_run}_scores.csv"
        )
        
        if not filename:
            return
            
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow(['Question ID', 'Category', 'Task', 'Score', 'Status', 
                                'Ground Truth', 'LLM Answer (truncated)'])
                
                # Data rows
                for score_record in self.scoring_results['scores']:
                    status = "Correct" if score_record['score'] >= 1.0 else \
                            "Partial" if score_record['score'] >= 0.5 else "Incorrect"
                    
                    writer.writerow([
                        score_record['question_id'],
                        score_record['category'],
                        score_record['task'],
                        score_record['score'],
                        status,
                        score_record['ground_truth'],
                        score_record['llm_answer']
                    ])
                
                # Summary rows
                writer.writerow([])
                writer.writerow(['Summary'])
                writer.writerow(['Total Questions', self.scoring_results['total_questions']])
                writer.writerow(['Overall Accuracy', f"{self.scoring_results['overall_accuracy']:.2f}%"])
                
                # Category summary
                writer.writerow([])
                writer.writerow(['Category', 'Correct', 'Total', 'Accuracy'])
                for category, scores in self.scoring_results['category_scores'].items():
                    accuracy = (scores['correct'] / scores['total'] * 100) if scores['total'] > 0 else 0
                    writer.writerow([category, scores['correct'], scores['total'], f"{accuracy:.2f}%"])
            
            messagebox.showinfo("Export Complete", f"Results exported to:\n{filename}")
            self.log_info(f"Scoring results exported to CSV: {filename}")

        except Exception as e:
            self.log_error(f"Failed to export scoring results to CSV {filename}: {e}")
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")
    
    def export_summary_report(self):
        """Export human-readable summary report"""
        if not self.scoring_results:
            return
            
        # Ask for save location
        filename = self.ask_save_file(
            title="Export Summary Report",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"{self.selected_run}_scoring_report.txt"
        )
        
        if not filename:
            return
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                # Get the displayed text
                content = self.results_text.get("1.0", tk.END)
                f.write(content)
                
                # Add additional details
                f.write("\n" + "="*50 + "\n")
                f.write("DETAILED SCORING INFORMATION\n")
                f.write("="*50 + "\n\n")
                
                # Run configuration
                run_info = self.scoring_results['run_metadata']
                f.write("Run Configuration:\n")
                f.write(f"- Dataset: {os.path.basename(run_info.get('dataset_path', 'unknown'))}\n")
                f.write(f"- Start Time: {run_info.get('start_time', 'unknown')}\n")
                f.write(f"- End Time: {run_info.get('end_time', 'unknown')}\n")
                f.write(f"- Status: {run_info.get('status', 'unknown')}\n")
                f.write(f"- Selected Questions: {run_info.get('selected_questions', [])}\n")
                
            messagebox.showinfo("Export Complete", f"Summary report exported to:\n{filename}")
            self.log_info(f"Summary report exported: {filename}")

        except Exception as e:
            self.log_error(f"Failed to export summary report {filename}: {e}")
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")
    
    def open_results_folder(self):
        """Open the results folder for selected run"""
        if not self.selected_run:
            return
            
        run_path = os.path.join(self.runs_dir, self.selected_run)
        if os.path.exists(run_path):
            from .base_components import open_folder_in_explorer
            open_folder_in_explorer(run_path)
