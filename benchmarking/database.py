"""
Unified database layer for ACO optimization persistence.

This module provides a single, consistent interface for storing and retrieving
optimization data, replacing the previous dual-system approach.
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from .interfaces import (
    OptimizationDatabase, TestCase, TestResult, RunMetadata,
    ParameterConverter, OptimizationError
)


class SQLiteOptimizationDatabase(OptimizationDatabase):
    """SQLite implementation of the optimization database interface"""
    
    def __init__(self, run_directory: Path):
        self.run_directory = Path(run_directory)
        self.db_path = self.run_directory / "optimization.db"
        
        # Ensure directory exists
        self.run_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database with all required tables"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Main test cases table - stores all individual test results
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    question_number INTEGER,
                    question_ground_truth TEXT,
                    parameters_json TEXT NOT NULL,
                    -- Phase marker: 'baseline' or 'aco' (default 'aco')
                    phase TEXT DEFAULT 'aco',
                    
                    -- Results
                    completed BOOLEAN DEFAULT 0,
                    score REAL,
                    response TEXT,
                    response_time REAL,
                    error_message TEXT,
                    timestamp TEXT,
                    
                    -- Rich data for analysis
                    slots_data TEXT,  -- JSON string
                    full_api_response TEXT,  -- JSON string
                    
                    UNIQUE(test_id)
                )
            """)
            
            # Algorithm state table - stores algorithm-specific persistence data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS algorithm_state (
                    id INTEGER PRIMARY KEY,
                    algorithm_name TEXT NOT NULL,
                    state_data TEXT NOT NULL,  -- JSON string
                    last_updated TEXT NOT NULL,
                    
                    UNIQUE(algorithm_name)
                )
            """)
            
            # Run metadata table - stores overall run information
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS run_metadata (
                    id INTEGER PRIMARY KEY,
                    run_name TEXT NOT NULL,
                    algorithm TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    status TEXT NOT NULL,
                    
                    -- Configuration
                    dataset_path TEXT NOT NULL,
                    selected_questions TEXT NOT NULL,  -- JSON array
                    total_questions INTEGER NOT NULL,
                    endpoint_type TEXT NOT NULL,
                    
                    -- Progress
                    total_combinations INTEGER,  -- NULL for dynamic algorithms
                    completed_combinations INTEGER DEFAULT 0,
                    
                    -- Results
                    best_score REAL,
                    best_parameters TEXT,  -- JSON string
                    
                    -- System
                    last_save_time TEXT,
                    error_message TEXT,
                    
                    -- Original config paths (nullable)
                    api_config_path TEXT,
                    server_config_path TEXT
                )
            """)

            # Backward-compatible migration: add columns if missing
            try:
                cursor.execute("PRAGMA table_info(run_metadata)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'api_config_path' not in cols:
                    cursor.execute("ALTER TABLE run_metadata ADD COLUMN api_config_path TEXT")
                if 'server_config_path' not in cols:
                    cursor.execute("ALTER TABLE run_metadata ADD COLUMN server_config_path TEXT")
            except Exception:
                pass
            
            # Performance optimization indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_completed ON test_cases(completed)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_score ON test_cases(score DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_parameters ON test_cases(parameters_json)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_phase ON test_cases(phase)")

            # Auto Mode snapshots table for policy/status telemetry
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auto_mode_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    contenders_count INTEGER,
                    target_coverage INTEGER
                )
            """)
            
            conn.commit()
    
    def save_test_result(self, test_case: TestCase, result: TestResult, phase: str = 'aco') -> None:
        """Save completed test result to database.

        phase: 'baseline' or 'aco' (default 'aco')
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Extract question info
            question_number = test_case.question.get('question_number', test_case.question_id)
            ground_truth = test_case.question.get('ground_truth', '')
            
            cursor.execute("""
                INSERT OR REPLACE INTO test_cases 
                (test_id, question_id, question_number, question_ground_truth,
                 parameters_json, phase, completed, score, response, response_time, 
                 error_message, timestamp, slots_data, full_api_response)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_case.test_id,
                test_case.question_id,
                question_number,
                ground_truth,
                json.dumps(test_case.parameters),
                phase,
                1,  # completed = True
                result.score,
                result.response,
                result.response_time,
                result.error_message,
                result.timestamp,
                json.dumps(result.slots_data) if result.slots_data else None,
                json.dumps(result.full_api_response) if result.full_api_response else None
            ))
            
            conn.commit()
    
    def get_top_combinations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top performing parameter combinations"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
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
    
    def get_progress_summary(self) -> Dict[str, int]:
        """Get summary of completed vs total test cases"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM test_cases")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM test_cases WHERE completed = 1")
            completed = cursor.fetchone()[0]
            
            return {
                "total": total,
                "completed": completed, 
                "remaining": total - completed
            }

    def get_completed_question_numbers_by_phase(self, phase: str = 'baseline') -> List[int]:
        """Return distinct question_number values with completed results for a given phase."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT question_number FROM test_cases WHERE completed = 1 AND phase = ?",
                (phase,)
            )
            rows = cursor.fetchall()
            return [int(r[0]) for r in rows if r and r[0] is not None]

    def get_baseline_correct_incorrect(self) -> Dict[str, List[int]]:
        """Compute correctness lists for baseline phase using stored scores.

        Returns a dict with keys 'correct' and 'incorrect' listing question_numbers.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT question_number, MAX(score) as max_score
                FROM test_cases
                WHERE completed = 1 AND phase = 'baseline' AND score IS NOT NULL
                GROUP BY question_number
                """
            )
            correct: List[int] = []
            incorrect: List[int] = []
            for qnum, max_score in cursor.fetchall():
                try:
                    qn = int(qnum) if qnum is not None else None
                except Exception:
                    qn = None
                if qn is None:
                    continue
                if max_score is not None and float(max_score) >= 1.0:
                    correct.append(qn)
                else:
                    incorrect.append(qn)
            return {"correct": sorted(correct), "incorrect": sorted(incorrect)}
    
    def get_incomplete_test_cases(self) -> List[TestCase]:
        """Get test cases that haven't been completed (for resume)"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT test_id, question_id, question_number, question_ground_truth,
                       parameters_json, score, response, response_time, error_message, timestamp
                FROM test_cases 
                WHERE completed = 0
                ORDER BY test_id
            """)
            
            incomplete_cases = []
            for row in cursor.fetchall():
                test_id, question_id, question_number, ground_truth, parameters_json, score, response, response_time, error_message, timestamp = row
                
                # Reconstruct question object from stored data
                question = {
                    'ground_truth': ground_truth,
                    'question_number': question_number
                }
                
                # Parse parameters
                parameters = json.loads(parameters_json)
                
                test_case = TestCase(
                    test_id=test_id,
                    question_id=question_id,
                    question=question,
                    parameters=parameters,
                    response=response,
                    score=score,
                    response_time=response_time,
                    error_message=error_message,
                    timestamp=timestamp
                )
                incomplete_cases.append(test_case)
            
            return incomplete_cases
    
    def save_algorithm_state(self, algorithm_name: str, state: Dict[str, Any]) -> None:
        """Save algorithm-specific state"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO algorithm_state 
                (algorithm_name, state_data, last_updated)
                VALUES (?, ?, ?)
            """, (
                algorithm_name,
                json.dumps(state),
                timestamp
            ))
            
            conn.commit()
    
    def load_algorithm_state(self, algorithm_name: str) -> Dict[str, Any]:
        """Load algorithm-specific state"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT state_data FROM algorithm_state 
                WHERE algorithm_name = ?
            """, (algorithm_name,))
            
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return {}
    
    def save_run_metadata(self, metadata: RunMetadata) -> None:
        """Save run metadata"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO run_metadata 
                (id, run_name, algorithm, start_time, end_time, status,
                 dataset_path, selected_questions, total_questions, endpoint_type,
                 total_combinations, completed_combinations, best_score, best_parameters,
                 last_save_time, error_message, api_config_path, server_config_path)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata.run_name,
                metadata.algorithm,
                metadata.start_time,
                metadata.end_time,
                metadata.status,
                metadata.dataset_path,
                json.dumps(metadata.selected_questions),
                metadata.total_questions,
                metadata.endpoint_type,
                metadata.total_combinations,
                metadata.completed_combinations,
                metadata.best_score,
                json.dumps(metadata.best_parameters) if metadata.best_parameters else None,
                metadata.last_save_time,
                metadata.error_message,
                getattr(metadata, 'api_config_path', None),
                getattr(metadata, 'server_config_path', None)
            ))
            
            conn.commit()
    
    def load_run_metadata(self) -> Optional[RunMetadata]:
        """Load run metadata (robust to legacy schemas)"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(run_metadata)")
            cols = [r[1] for r in cursor.fetchall()]
            cursor.execute("SELECT * FROM run_metadata WHERE id = 1")
            row = cursor.fetchone()
            if not row:
                return None
            data = {cols[i]: row[i] for i in range(min(len(cols), len(row)))}

            # Parse JSON fields
            selected_questions = json.loads(data.get('selected_questions') or '[]')
            best_parameters = json.loads(data.get('best_parameters')) if data.get('best_parameters') else None

            return RunMetadata(
                run_name=data.get('run_name', ''),
                algorithm=data.get('algorithm', ''),
                start_time=data.get('start_time', ''),
                status=data.get('status', ''),
                dataset_path=data.get('dataset_path', ''),
                selected_questions=selected_questions,
                total_questions=int(data.get('total_questions') or 0),
                endpoint_type=data.get('endpoint_type', ''),
                total_combinations=data.get('total_combinations'),
                completed_combinations=int(data.get('completed_combinations') or 0),
                best_score=data.get('best_score'),
                best_parameters=best_parameters,
                last_save_time=data.get('last_save_time'),
                end_time=data.get('end_time'),
                error_message=data.get('error_message'),
                api_config_path=data.get('api_config_path'),
                server_config_path=data.get('server_config_path')
            )
    
    def update_progress(self, completed_combinations: int, best_score: Optional[float] = None,
                       best_parameters: Optional[Dict[str, Any]] = None) -> None:
        """Update progress information in metadata"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            if best_score is not None and best_parameters is not None:
                cursor.execute("""
                    UPDATE run_metadata 
                    SET completed_combinations = ?, best_score = ?, best_parameters = ?, last_save_time = ?
                    WHERE id = 1
                """, (
                    completed_combinations,
                    best_score,
                    json.dumps(best_parameters),
                    timestamp
                ))
            else:
                cursor.execute("""
                    UPDATE run_metadata 
                    SET completed_combinations = ?, last_save_time = ?
                    WHERE id = 1
                """, (completed_combinations, timestamp))
            
            conn.commit()
    
    def close(self) -> None:
        """Close database connections (no persistent connections in this implementation)"""
        # SQLite connections are created per-operation, so nothing to close
        pass

    # ---------- Auto Mode snapshots ----------
    def save_auto_mode_snapshot(self, contenders_count: int, target_coverage: int) -> None:
        from datetime import datetime
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO auto_mode_snapshots (timestamp, contenders_count, target_coverage) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), int(contenders_count), int(target_coverage))
            )
            conn.commit()

    def get_latest_auto_mode_snapshot(self) -> Dict[str, Any]:
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
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics for debugging/monitoring"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Get table sizes
                cursor.execute("SELECT COUNT(*) FROM test_cases")
                test_cases_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM algorithm_state")
                algorithm_states_count = cursor.fetchone()[0]
                
                # Get database file size
                db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
                db_size_mb = db_size_bytes / (1024 * 1024)
                
                return {
                    'database_path': str(self.db_path),
                    'database_size_mb': round(db_size_mb, 2),
                    'test_cases_count': test_cases_count,
                    'algorithm_states_count': algorithm_states_count,
                    'last_modified': datetime.fromtimestamp(self.db_path.stat().st_mtime).isoformat() if self.db_path.exists() else None
                }
        except Exception as e:
            logging.error(f"Error getting database stats: {e}")
            return {'error': str(e)}


def create_test_case_from_parameters(
    question_id: int,
    question: Dict[str, Any], 
    parameters: Dict[str, Any],
    test_id: Optional[int] = None
) -> TestCase:
    """Utility function to create TestCase from parameters"""
    if test_id is None:
        # Generate unique test ID based on timestamp
        test_id = int(datetime.now().timestamp() * 1000000)
    
    return TestCase(
        test_id=test_id,
        question_id=question_id,
        question=question,
        parameters=parameters
    )
