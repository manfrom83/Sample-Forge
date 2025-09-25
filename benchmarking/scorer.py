"""
Flexible Scoring System
Category-agnostic scoring engine with EXACT and PARTIAL modes
Enhanced normalization to reduce common false negatives (hyphens, suffix words, trailing conjunctions)
and word-to-number conversion for zebra puzzles.
"""

import re
import unicodedata
from typing import List, Tuple, Optional


class FlexibleScorer:
    """Category-agnostic scoring engine with enhanced normalization"""
    
    def __init__(self):
        # Answer extraction patterns (from LiveBench analysis)
        self.extraction_patterns = [
            # Solution tags
            (r'<solution>(.*?)</solution>', re.DOTALL | re.IGNORECASE),
            # Boxed math answers
            (r'\\boxed\{(.*?)\}', 0),
            # Markdown emphasis (handles *, **, and *** on each side)
            (r'\*{1,3}(.*?)\*{1,3}', 0),
            # Answer: prefix
            (r'[Aa]nswer:\s*(.*?)(?:\n|$)', 0),
            # Final answer: prefix
            (r'[Ff]inal [Aa]nswer:\s*(.*?)(?:\n|$)', 0),
        ]
        
        # Word-to-number conversion for zebra puzzles (added for LiveBench compatibility)
        self.word_to_num = {
            'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
            'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10'
        }

        # Stopwords/suffix tokens commonly present in short labels
        # These are removed during token comparison to avoid false negatives:
        # e.g., "romance movies" vs "romance"
        self.label_stopwords = {
            'movie', 'movies', 'film', 'films', 'genre', 'genres', 'type', 'types',
            'category', 'categories', 'the', 'a', 'an', 'answer', 'final', 'label'
        }
    
    def score_answer(self, ground_truth: str, llm_answer: str, 
                     scoring_mode: str = "EXACT") -> float:
        """
        Score any answer based on mode, not category
        
        Args:
            ground_truth: Expected answer (can be multi-part)
            llm_answer: Model's response
            scoring_mode: "EXACT" or "PARTIAL"
            
        Returns:
            Score between 0.0 and 1.0
        """
        # Extract answer from various formats
        extracted = self.extract_answer(llm_answer)
        
        # Parse multi-part answers
        gt_parts = self.parse_answer_parts(ground_truth)
        answer_parts = self.parse_answer_parts(extracted)
        
        if scoring_mode == "EXACT":
            # For single-label ground truths, accept match against any provided part
            if len(gt_parts) == 1:
                gt = gt_parts[0]
                for part in answer_parts:
                    if self.parts_match(gt, part):
                        return 1.0
                return 0.0
            # For multi-part, all parts must match exactly in order
            return 1.0 if self.lists_match_exactly(gt_parts, answer_parts) else 0.0
        
        elif scoring_mode == "PARTIAL":
            # Calculate percentage of correct parts
            if not gt_parts:
                return 0.0
            
            correct = 0
            for i, gt_part in enumerate(gt_parts):
                if i < len(answer_parts) and self.parts_match(gt_part, answer_parts[i]):
                    correct += 1
            
            return correct / len(gt_parts)
        
        else:
            raise ValueError(f"Unknown scoring mode: {scoring_mode}")
    
    def remove_thinking_content(self, text: str) -> str:
        """
        Remove thinking content from text before scoring
        Handles variations of <think>...</think> tags with case and spacing flexibility
        """
        # Pattern for think tags with variations:
        # - Case insensitive: think, THINK, Think, ThInK, etc.
        # - Optional spaces around the word: < think >, <think >, < think>
        # - Captures everything between opening and closing tags
        think_pattern = r'<\s*think\s*>.*?</\s*think\s*>'
        
        # Remove all thinking blocks (case insensitive, multiline)
        cleaned_text = re.sub(think_pattern, '', text, flags=re.DOTALL | re.IGNORECASE)
        
        return cleaned_text
    
    def extract_answer(self, llm_answer: str) -> str:
        """Extract answer from various formats"""
        # FIRST: Remove thinking content before any processing
        cleaned_response = self.remove_thinking_content(llm_answer)
        
        # Try each extraction pattern - use LAST match for better answer extraction
        for pattern, flags in self.extraction_patterns:
            if flags:
                matches = re.findall(pattern, cleaned_response, flags)
            else:
                matches = re.findall(pattern, cleaned_response)
            
            if matches:
                # Take the LAST match (final answer usually at end)
                return matches[-1].strip()
        
        # Fallback: try last line
        lines = cleaned_response.strip().split('\n')
        if lines:
            last_line = lines[-1].strip()
            # Check if last line looks like an answer
            if len(last_line) < 200:  # Reasonable answer length
                return last_line
        
        # Final fallback: return full response
        return cleaned_response.strip()
    
    def parse_answer_parts(self, answer: str) -> List[str]:
        """Parse multi-part answers"""
        # Check for comma-separated
        if ',' in answer:
            parts = [p.strip() for p in answer.split(',')]
            return parts
        
        # Check for newline-separated
        if '\n' in answer:
            parts = [p.strip() for p in answer.split('\n') if p.strip()]
            return parts
        
        # Check for semicolon-separated
        if ';' in answer:
            parts = [p.strip() for p in answer.split(';')]
            return parts
        
        # Single answer
        return [answer.strip()]
    
    def parts_match(self, expected: str, actual: str) -> bool:
        """Check if two answer parts match with robust normalization"""
        # Normalize both simple strings
        expected_norm = self.normalize_answer(expected)
        actual_norm = self.normalize_answer(actual)

        # Exact string match
        if expected_norm == actual_norm:
            return True

        # Numeric comparison with tolerance
        try:
            expected_num = float(expected_norm)
            actual_num = float(actual_norm)
            return abs(expected_num - actual_num) < 1e-6
        except ValueError:
            pass

        # Token-based comparison with stopword filtering and hyphen/space equivalence
        exp_tokens = self.tokenize_answer(expected_norm)
        act_tokens = self.tokenize_answer(actual_norm)

        # If either reduces to empty after tokenization, fall back to strict False
        if not exp_tokens or not act_tokens:
            return False

        exp_set = set(exp_tokens)
        act_set = set(act_tokens)

        # Accept if expected tokens are a subset of actual tokens or vice versa
        # Examples:
        #  - expected: ["romance"], actual: ["romance", "movies"] -> True
        #  - expected: ["police", "officer"], actual: ["police-officer"] -> True via tokenization
        if exp_set.issubset(act_set) or act_set.issubset(exp_set):
            return True

        # As a final lenient check, accept substring at token boundaries
        exp_join = ' '.join(exp_tokens)
        act_join = ' '.join(act_tokens)
        if exp_join in act_join or act_join in exp_join:
            return True

        return False
    
    def lists_match_exactly(self, expected: List[str], actual: List[str]) -> bool:
        """Check if two lists match exactly"""
        if len(expected) != len(actual):
            return False
        
        for exp, act in zip(expected, actual):
            if not self.parts_match(exp, act):
                return False
        
        return True
    
    def normalize_answer(self, answer: str) -> str:
        """Normalize raw text: casefold, Unicode normalize, basic cleanup"""
        if not isinstance(answer, str):
            answer = str(answer)

        # Unicode normalize (e.g., different hyphen codepoints)
        answer = unicodedata.normalize('NFKC', answer)

        # Lowercase and collapse whitespace
        answer = ' '.join(answer.lower().split())

        # Remove trailing conjunction artifacts like "or" / "and" at end
        answer = re.sub(r"\s+(or|and)\s*$", "", answer)

        # Replace various dashes/underscores with spaces to equalize tokens
        # Replace dashes/underscores with spaces to equalize tokens (ASCII-only)
        answer = re.sub(r"[-_]+", " ", answer)
        # Remove common enclosing punctuation and trailing punctuation
        answer = answer.strip().strip('"\'`()[]{}')
        answer = answer.rstrip('.,;:!?')

        # Word-to-number conversion (simple cases)
        for word, num in self.word_to_num.items():
            # replace whole words only
            answer = re.sub(rf"\b{re.escape(word)}\b", num, answer)

        # Common replacements for booleans/shortcuts
        replacements = {
            'true': 'yes',
            'false': 'no',
            't': 'yes',
            'f': 'no',
        }
        if answer in replacements:
            answer = replacements[answer]

        return answer

    def tokenize_answer(self, text: str) -> List[str]:
        """Tokenize into words, dropping stopwords and empty tokens"""
        # Remove residual punctuation to prefer token boundaries
        text = re.sub(r"[^0-9a-zA-Z\s]+", " ", text)
        tokens = [t for t in text.split() if t]
        # Drop label stopwords
        tokens = [t for t in tokens if t not in self.label_stopwords]
        return tokens
    
