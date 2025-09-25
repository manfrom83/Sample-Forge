"""
ACO Database Viewer for New Clean Architecture
Works with the unified optimization.db format from the refactored ACO system
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from benchmarking.interfaces import ParameterConverter
from utils.logger import logger


class StandaloneACODatabaseViewer:
    """Database viewer for the new clean ACO optimization system"""
    
    def __init__(self, run_directory: Path):
        self.run_directory = run_directory
        # NEW: Uses optimization.db from the clean architecture
        self.db_path = run_directory / "optimization.db"
    
    def database_exists(self) -> bool:
        """Check if the database file exists"""
        return self.db_path.exists()
    
    def get_top_parameter_combinations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top performing parameter combinations from completed test cases"""
        if not self.database_exists():
            return []
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Updated query for new schema
                cursor.execute("""
                    SELECT parameters_json, 
                           AVG(score) as avg_score,
                           COUNT(*) as question_count,
                           SUM(CASE WHEN score >= 1.0 THEN 1 ELSE 0 END) as correct_count
                    FROM test_cases 
                    WHERE completed = 1 AND score IS NOT NULL
                    GROUP BY parameters_json
                    ORDER BY avg_score DESC, correct_count DESC
                    LIMIT ?
                """, (limit,))
                
                top_combinations = []
                for row in cursor.fetchall():
                    parameters_json, avg_score, question_count, correct_count = row
                    parameters = json.loads(parameters_json)
                    
                    # Format parameters for display
                    param_display = " / ".join([f"{k}: {v}" for k, v in parameters.items()])
                    
                    top_combinations.append({
                        'parameters': parameters,
                        'parameters_display': param_display,
                        'avg_score': avg_score,
                        'question_count': question_count,
                        'correct_count': correct_count,
                        'accuracy': f"{correct_count}/{question_count}"
                    })
                
                return top_combinations
                
        except Exception as e:
            logger.error(f"Error reading database: {e}")
            return []
    
    def get_progress_summary(self) -> Dict[str, int]:
        """Get progress summary of the run"""
        if not self.database_exists():
            return {'completed': 0, 'total': 0, 'remaining': 0}
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Count total and completed test cases
                cursor.execute("SELECT COUNT(*) FROM test_cases")
                total = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM test_cases WHERE completed = 1")
                completed = cursor.fetchone()[0]
                
                remaining = total - completed
                
                return {
                    'completed': completed,
                    'total': total,
                    'remaining': remaining
                }
                
        except Exception as e:
            logger.error(f"Error getting progress: {e}")
            return {'completed': 0, 'total': 0, 'remaining': 0}
    
    def get_all_test_cases(self, limit: int = None, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all test cases with optional pagination"""
        if not self.database_exists():
            return []
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Query compatible with new schema
                query = """
                    SELECT id, test_id, question_id, question_number, question_ground_truth,
                           parameters_json, score, response, response_time, timestamp,
                           slots_data, full_api_response, error_message
                    FROM test_cases 
                    WHERE completed = 1
                    ORDER BY id DESC
                """
                
                if limit:
                    query += f" LIMIT {limit} OFFSET {offset}"
                
                cursor.execute(query)
                
                test_cases = []
                for row in cursor.fetchall():
                    (id, test_id, question_id, question_number, question_ground_truth,
                     parameters_json, score, response, response_time, timestamp,
                     slots_data, full_api_response, error_message) = row
                    
                    parameters = json.loads(parameters_json) if parameters_json else {}
                    slots_data_parsed = json.loads(slots_data) if slots_data else {}
                    full_api_response_parsed = json.loads(full_api_response) if full_api_response else {}
                    
                    test_cases.append({
                        'id': id,
                        'test_id': test_id,
                        'question_id': question_id,
                        'question_number': question_number,
                        'ground_truth': question_ground_truth,
                        'parameters': parameters,
                        'score': score,
                        'response': response,
                        'response_time': response_time,
                        'timestamp': timestamp,
                        'slots_data': slots_data_parsed,
                        'full_api_response': full_api_response_parsed,
                        'error_message': error_message
                    })
                
                return test_cases
                
        except Exception as e:
            logger.error(f"Error getting test cases: {e}")
            return []

    # -------- Insights helpers (Python-side aggregation) --------

    def _load_all_completed(self) -> List[Dict[str, Any]]:
        """Load all completed test_cases as Python dicts (parameters parsed)."""
        if not self.database_exists():
            return []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT question_number, question_id, parameters_json, score, phase
                    FROM test_cases
                    WHERE completed = 1 AND score IS NOT NULL
                    """
                )
                rows = cursor.fetchall()
                out = []
                for qnum, qid, pjson, score, phase in rows:
                    try:
                        params = json.loads(pjson) if pjson else {}
                    except Exception:
                        params = {}
                    out.append({
                        'question_number': qnum,
                        'question_id': qid,
                        'parameters': params,
                        'score': score,
                        'phase': phase,
                    })
                return out
        except Exception as e:
            logger.error(f"Error loading completed cases: {e}")
            return []

    def summarize_top_combinations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return top parameter combinations with their correct-question list."""
        records = self._load_all_completed()
        # Determine total questions in the dataset used by this run
        question_total = 0
        try:
            meta = self.get_run_metadata()
            ds_path = meta.get('dataset_path')
            if ds_path and Path(ds_path).exists():
                try:
                    # Lightweight count: number of question sections in exported dataset
                    content = Path(ds_path).read_text(encoding='utf-8', errors='ignore')
                    # Count occurrences of the section separator used by DatasetParser
                    question_total = max(0, content.count('--- Question '))
                except Exception:
                    question_total = 0
        except Exception:
            question_total = 0
        if question_total <= 0:
            # Fallback: count unique questions observed in DB
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(DISTINCT COALESCE(question_number, question_id)) FROM test_cases")
                    row = cur.fetchone()
                    if row and row[0]:
                        question_total = int(row[0])
            except Exception:
                question_total = 0
        if question_total <= 0:
            # Last resort: use run_metadata total_questions (may reflect selected subset)
            try:
                tq = int(meta.get('total_questions') or 0)
                if tq > 0:
                    question_total = tq
            except Exception:
                pass
        groups: Dict[Tuple, Dict[str, Any]] = {}
        for r in records:
            # Use a hashable key that normalizes lists/dicts
            key = ParameterConverter.make_hashable_key(r['parameters'])
            g = groups.setdefault(key, {
                'parameters': r['parameters'],
                'scores': [],
                'correct_q': set()
            })
            g['scores'].append(r['score'])
            if r['score'] >= 1.0:
                qn = r['question_number'] or r['question_id']
                if qn is not None:
                    try:
                        g['correct_q'].add(int(qn))
                    except Exception:
                        pass
        results = []
        for g in groups.values():
            scores = g['scores']
            avg = sum(scores)/len(scores) if scores else 0.0
            correct_count = sum(1 for s in scores if s >= 1.0)
            results.append({
                'parameters': g['parameters'],
                'avg_score': avg,
                'correct_count': correct_count,
                'question_count': len(scores),  # tested so far for this combo
                'question_total': question_total,
                'correct_questions': sorted(list(g['correct_q']))
            })
        results.sort(key=lambda x: (x['avg_score'], x['correct_count']), reverse=True)
        return results[:limit]

    def summarize_param_value_correlations(self, top_n: int = 10, bottom_n: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """Compute per-parameter value correlation (avg score, counts)."""
        records = self._load_all_completed()
        stats: Dict[Tuple[str, str], List[float]] = {}
        for r in records:
            for k, v in r['parameters'].items():
                stats.setdefault((k, str(v)), []).append(r['score'])
        entries = []
        for (k, v), arr in stats.items():
            avg = sum(arr)/len(arr) if arr else 0.0
            correct = sum(1 for s in arr if s >= 1.0)
            entries.append({'param': k, 'value': v, 'avg_score': avg, 'count': len(arr), 'correct': correct})
        entries.sort(key=lambda x: (x['avg_score'], x['correct'], x['count']), reverse=True)
        top = entries[:top_n]
        # Worst by avg (ascending) then higher count
        entries.sort(key=lambda x: (x['avg_score'], -x['count']))
        bottom = entries[:bottom_n]
        return {'top': top, 'bottom': bottom}

    def summarize_param_pair_correlations(self, top_n: int = 10, bottom_n: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """Compute pairwise (param=value) correlations."""
        records = self._load_all_completed()
        pair_stats: Dict[Tuple[Tuple[str, str], Tuple[str, str]], List[float]] = {}
        for r in records:
            items = sorted([(k, str(v)) for k, v in r['parameters'].items()])
            # All unique pairs
            for i in range(len(items)):
                for j in range(i+1, len(items)):
                    a = items[i]
                    b = items[j]
                    key = (a, b)
                    pair_stats.setdefault(key, []).append(r['score'])
        pairs = []
        for key, arr in pair_stats.items():
            avg = sum(arr)/len(arr) if arr else 0.0
            correct = sum(1 for s in arr if s >= 1.0)
            (p1, v1), (p2, v2) = key
            pairs.append({
                'pair': ((p1, v1), (p2, v2)),
                'avg_score': avg,
                'count': len(arr),
                'correct': correct
            })
        pairs.sort(key=lambda x: (x['avg_score'], x['correct'], x['count']), reverse=True)
        top = pairs[:top_n]
        pairs.sort(key=lambda x: (x['avg_score'], -x['count']))
        bottom = pairs[:bottom_n]
        return {'top': top, 'bottom': bottom}
    
    def get_run_metadata(self) -> Dict[str, Any]:
        """Get run metadata from the database"""
        if not self.database_exists():
            return {}
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Try to get metadata from run_metadata table
                cursor.execute("""
                    SELECT run_name, algorithm, start_time, end_time, status,
                           dataset_path, selected_questions, total_questions,
                           endpoint_type, completed_combinations, best_score, best_parameters
                    FROM run_metadata
                    ORDER BY id DESC
                    LIMIT 1
                """)
                
                row = cursor.fetchone()
                if row:
                    (run_name, algorithm, start_time, end_time, status,
                     dataset_path, selected_questions, total_questions,
                     endpoint_type, completed_combinations, best_score, best_parameters) = row
                    
                    return {
                        'run_name': run_name,
                        'algorithm': algorithm,
                        'start_time': start_time,
                        'end_time': end_time,
                        'status': status,
                        'dataset_path': dataset_path,
                        'selected_questions': json.loads(selected_questions) if selected_questions else [],
                        'total_questions': total_questions,
                        'endpoint_type': endpoint_type,
                        'completed_combinations': completed_combinations,
                        'best_score': best_score,
                        'best_parameters': json.loads(best_parameters) if best_parameters else {}
                    }
                
                return {}
                
        except Exception as e:
            logger.error(f"Error getting run metadata: {e}")
            return {}
    
    def get_algorithm_state(self) -> Dict[str, Any]:
        """Get algorithm state if available"""
        if not self.database_exists():
            return {}

    def get_latest_snapshot(self) -> Dict[str, Any]:
        """Return latest Auto Mode snapshot with contenders and target coverage, if available."""
        if not self.database_exists():
            return {}
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT timestamp, contenders_count, target_coverage FROM auto_mode_snapshots ORDER BY id DESC LIMIT 1"
                )
                row = cursor.fetchone()
                if row:
                    ts, c, t = row
                    return {"timestamp": ts, "contenders_count": c, "target_coverage": t}
                return {}
        except Exception:
            return {}
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT algorithm_name, state_data, last_updated
                    FROM algorithm_state
                    ORDER BY id DESC
                    LIMIT 1
                """)
                
                row = cursor.fetchone()
                if row:
                    algorithm_name, state_data, last_updated = row
                    return {
                        'algorithm_name': algorithm_name,
                        'state': json.loads(state_data) if state_data else {},
                        'last_updated': last_updated
                    }
                
                return {}
                
        except Exception as e:
            # Algorithm state table might not exist in all databases
            return {}
