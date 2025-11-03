"""
Enhanced Log Analyzer for Video Transcriber Server Logs v3.0
AI-Optimized for Debugging Assistance

DESIGNED FOR AI ASSISTANTS TO:
- Understand WHAT happened, WHY it happened, and HOW to fix it
- Get exact file paths, line numbers, and suggested fixes
- See patterns across time, operations, and resources
- Predict what might break next
- Navigate directly to problematic code

Features:
✅ Root cause analysis with fix suggestions
✅ Time-series patterns (hourly/daily/weekly)
✅ Semantic error categorization
✅ Actionable remediation steps
✅ Context reconstruction (what user was doing)
✅ Resource correlation (CPU/RAM impact)
✅ Quick navigation links
✅ Predictive failure analysis

Usage:
    python scripts/analyze_logs.py
    python scripts/analyze_logs.py --log-file logs/custom.log
    python scripts/analyze_logs.py --output report.txt
    python scripts/analyze_logs.py --json report.json (AI-parseable format)
"""

import re
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional, Set


class LogAnalyzer:
    """AI-Optimized Log Analyzer for Video Transcriber"""
    
    # Knowledge base of common errors and fixes
    FIX_SUGGESTIONS = {
        'FileNotFoundError': {
            'audio.wav': {
                'diagnosis': 'FFmpeg failed to extract audio or file was deleted during processing',
                'fix': 'Check FFmpeg installation, verify input file exists, check disk space',
                'file': 'src/services/processor.py',
                'prevention': 'Add file existence check before processing, implement proper cleanup'
            },
            'model': {
                'diagnosis': 'AI model file missing or incorrect path',
                'fix': 'Download model with: python scripts/download_models.py',
                'file': 'src/services/model_cache.py',
                'prevention': 'Implement model validation at startup'
            }
        },
        'RuntimeError': {
            'mat1 and mat2 shapes': {
                'diagnosis': 'Dimension mismatch in neural network - incompatible model weights or inputs',
                'fix': 'Retrain model OR fix input dimensions in hybrid_router.py',
                'file': 'src/models/hybrid_router.py',
                'prevention': 'Add dimension validation before forward pass'
            },
            'CUDA': {
                'diagnosis': 'GPU memory exhausted or CUDA driver issue',
                'fix': 'Reduce batch size, clear GPU cache, or use CPU mode',
                'file': 'config/default.yaml',
                'prevention': 'Implement GPU memory monitoring'
            }
        },
        'NameError': {
            'not defined': {
                'diagnosis': 'Missing import or typo in variable name',
                'fix': 'Add missing import statement or fix variable name',
                'file': 'Check module in error traceback',
                'prevention': 'Use type hints and linting'
            }
        },
        'subprocess.CalledProcessError': {
            'ffmpeg': {
                'diagnosis': 'FFmpeg command failed - invalid file, codec issue, or corrupted media',
                'fix': 'Check ffmpeg/bin/ffmpeg.exe exists, validate input file format',
                'file': 'src/services/processor.py',
                'prevention': 'Validate media file before processing, add format detection'
            }
        },
        'UnboundLocalError': {
            'audio_path': {
                'diagnosis': 'Variable used before assignment - control flow issue',
                'fix': 'Initialize variable before try/except block OR refactor error handling',
                'file': 'src/services/processor_progress.py',
                'prevention': 'Always initialize variables at function start'
            }
        }
    }
    
    def __init__(self, log_path: Path, include_rotated: bool = True, 
                 db_path: Optional[Path] = None, output_dir: Optional[Path] = None):
        self.log_path = log_path
        self.include_rotated = include_rotated
        self.db_path = db_path or Path('processed.db')
        self.output_dir = output_dir or Path('output')
        
        # Multi-source data
        self.db_videos: Dict = {}  # Data from database
        self.output_videos: Set[str] = set()  # Videos in output folder
        self.missing_videos: List[Dict] = []  # In DB but not in output
        self.orphaned_videos: List[str] = []  # In output but not in DB
        
        # Log entry pattern: YYYY-MM-DD HH:MM:SS | LEVEL | Thread/Process | Module:Line | Message
        self.log_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+)\s+\| ([^|]+) \| ([^|]+) \| (.+)$'
        )
        
        # Statistics
        self.stats = {
            'total_lines': 0,
            'total_entries': 0,
            'errors': 0,
            'warnings': 0,
            'info': 0,
            'debug': 0,
            'crashes': 0
        }
        
        # Collections
        self.errors: List[Dict] = []
        self.warnings: List[Dict] = []
        self.crashes: List[Dict] = []
        self.important_events: List[Dict] = []
        self.resource_warnings: List[Dict] = []
        
        # Error grouping
        self.error_types: Counter = Counter()
        self.exception_types: Counter = Counter()
        
        # NEW: Advanced tracking
        self.error_hashes: Set[str] = set()  # Detect duplicate errors
        self.video_contexts: Counter = Counter()  # Track which videos have errors
        self.api_performance: List[Dict] = []  # API response times
        self.error_bursts: List[Dict] = []  # Time clusters of errors
        self.cascading_exceptions: List[Dict] = []  # Exception chains
        
        # NEW: Time-series analysis
        self.errors_by_hour: defaultdict = defaultdict(int)
        self.errors_by_day: defaultdict = defaultdict(int)
        self.warnings_by_hour: defaultdict = defaultdict(int)
        self.hourly_activity: defaultdict = defaultdict(lambda: {'errors': 0, 'warnings': 0, 'requests': 0})
        self.daily_summary: defaultdict = defaultdict(lambda: {
            'errors': 0, 'warnings': 0, 'info': 0, 
            'api_calls': 0, 'slow_requests': 0, 'videos_processed': set()
        })
        
        # NEW: AI categorization metadata
        self.error_categories: defaultdict = defaultdict(list)  # Semantic grouping
        self.operation_types: Counter = Counter()  # What operations were happening
        self.affected_modules: Counter = Counter()  # Which modules have issues
        self.user_activity: List[Dict] = []  # User actions and patterns
        
        # Current traceback collection
        self.current_traceback: Optional[List[str]] = None
        self.current_error: Optional[Dict] = None
        self.last_error_time: Optional[datetime] = None
    
    def analyze(self) -> Dict:
        """
        Analyze log files + database + output folder for holistic intelligence
        
        Returns:
            Dictionary with analysis results
        """
        print(f"📊 Multi-source Analysis Starting...")
        print(f"   Logs: {self.log_path}")
        
        # Step 1: Analyze main log file
        if not self.log_path.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_path}")
        
        with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                self.stats['total_lines'] = line_num
                self._process_line(line.rstrip())
        
        # Step 2: Analyze rotated log files
        if self.include_rotated:
            rotated_logs = self._discover_rotated_logs()
            if rotated_logs:
                print(f"   Found {len(rotated_logs)} rotated log files")
                for log_file in rotated_logs:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            self.stats['total_lines'] += 1
                            self._process_line(line.rstrip())
        
        # Step 3: Query database
        if self.db_path.exists():
            print(f"   Database: {self.db_path}")
            self._analyze_database()
        
        # Step 4: Scan output folder
        if self.output_dir.exists():
            print(f"   Output: {self.output_dir}")
            self._scan_output_folder()
        
        # Step 5: Cross-reference data sources
        self._cross_reference_data()
        
        # Finalize any pending traceback
        if self.current_traceback and self.current_error:
            self._finalize_error()
        
        print(f"✓ Analysis complete: {self.stats['total_entries']} log entries processed")
        print(f"✓ Database: {len(self.db_videos)} videos found")
        print(f"✓ Output: {len(self.output_videos)} video folders found")
        
        return {
            'stats': self.stats,
            'errors': self.errors,
            'warnings': self.warnings,
            'crashes': self.crashes,
            'important_events': self.important_events,
            'resource_warnings': self.resource_warnings,
            'error_types': self.error_types,
            'exception_types': self.exception_types
        }
    
    def _discover_rotated_logs(self) -> List[Path]:
        """Find all rotated log files (server.log.1, server.log.2, etc.)"""
        rotated = []
        base_name = self.log_path.stem  # 'server'
        parent = self.log_path.parent
        
        # Look for .log.1, .log.2, etc.
        for i in range(1, 10):  # Check up to .log.9
            rotated_path = parent / f"{base_name}.log.{i}"
            if rotated_path.exists():
                rotated.append(rotated_path)
        
        return sorted(rotated)  # Process in order
    
    def _analyze_database(self):
        """Extract video processing data from database - Auto-discovers schema"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # STEP 1: Discover all tables in database
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            if not tables:
                print(f"⚠️  Database has no tables")
                conn.close()
                return
            
            print(f"   Found tables: {', '.join(tables)}")
            
            # STEP 2: Find video/processing table (try common patterns)
            video_table = None
            for table in tables:
                if any(keyword in table.lower() for keyword in ['video', 'process', 'job', 'task']):
                    video_table = table
                    break
            
            if not video_table:
                # Use first table as fallback
                video_table = tables[0]
                print(f"   No video table found, using first table: {video_table}")
            
            # STEP 3: Get table schema
            cursor.execute(f"PRAGMA table_info({video_table})")
            columns = {row[1]: row[2] for row in cursor.fetchall()}  # name: type
            print(f"   Table '{video_table}' has {len(columns)} columns")
            
            # STEP 4: Build flexible query based on available columns
            id_col = self._find_column(columns, ['video_id', 'id', 'job_id', 'task_id'])
            filename_col = self._find_column(columns, ['filename', 'file', 'name', 'title'])
            status_col = self._find_column(columns, ['status', 'state'])
            duration_col = self._find_column(columns, ['duration', 'length', 'time'])
            lang_col = self._find_column(columns, ['language', 'lang', 'detected_language'])
            proc_time_col = self._find_column(columns, ['processing_time', 'proc_time', 'elapsed'])
            created_col = self._find_column(columns, ['created_at', 'created', 'timestamp', 'start_time'])
            completed_col = self._find_column(columns, ['completed_at', 'completed', 'finished_at', 'end_time'])
            error_col = self._find_column(columns, ['error_message', 'error', 'error_msg', 'failure_reason'])
            
            if not id_col:
                print(f"⚠️  Could not find ID column in {video_table}")
                conn.close()
                return
            
            # STEP 5: Build dynamic SELECT query
            select_parts = [id_col]
            col_mapping = {'id': id_col}
            
            if filename_col:
                select_parts.append(filename_col)
                col_mapping['filename'] = filename_col
            if status_col:
                select_parts.append(status_col)
                col_mapping['status'] = status_col
            if duration_col:
                select_parts.append(duration_col)
                col_mapping['duration'] = duration_col
            if lang_col:
                select_parts.append(lang_col)
                col_mapping['language'] = lang_col
            if proc_time_col:
                select_parts.append(proc_time_col)
                col_mapping['processing_time'] = proc_time_col
            if created_col:
                select_parts.append(created_col)
                col_mapping['created_at'] = created_col
            if completed_col:
                select_parts.append(completed_col)
                col_mapping['completed_at'] = completed_col
            if error_col:
                select_parts.append(error_col)
                col_mapping['error_message'] = error_col
            
            query = f"SELECT {', '.join(select_parts)} FROM {video_table}"
            if created_col:
                query += f" ORDER BY {created_col} DESC"
            
            # STEP 6: Execute and extract data
            cursor.execute(query)
            
            for row in cursor.fetchall():
                video_id = row[col_mapping['id']]
                
                self.db_videos[video_id] = {
                    'video_id': video_id,
                    'filename': row[col_mapping['filename']] if 'filename' in col_mapping else None,
                    'status': row[col_mapping['status']] if 'status' in col_mapping else 'unknown',
                    'duration': row[col_mapping['duration']] if 'duration' in col_mapping else None,
                    'language': row[col_mapping['language']] if 'language' in col_mapping else None,
                    'processing_time': row[col_mapping['processing_time']] if 'processing_time' in col_mapping else None,
                    'created_at': row[col_mapping['created_at']] if 'created_at' in col_mapping else None,
                    'completed_at': row[col_mapping['completed_at']] if 'completed_at' in col_mapping else None,
                    'error_message': row[col_mapping['error_message']] if 'error_message' in col_mapping else None
                }
            
            conn.close()
            print(f"   ✓ Loaded {len(self.db_videos)} videos from database")
            
        except Exception as e:
            print(f"⚠️  Could not read database: {e}")
            import traceback
            traceback.print_exc()
    
    def _find_column(self, columns: Dict[str, str], candidates: List[str]) -> Optional[str]:
        """Find first matching column name from candidates"""
        for candidate in candidates:
            # Try exact match first
            if candidate in columns:
                return candidate
            # Try case-insensitive match
            for col in columns:
                if col.lower() == candidate.lower():
                    return col
        return None
    
    def _scan_output_folder(self):
        """Scan output folder to find which videos have generated files"""
        try:
            for video_dir in self.output_dir.iterdir():
                if video_dir.is_dir():
                    video_id = video_dir.name
                    self.output_videos.add(video_id)
        except Exception as e:
            print(f"⚠️  Could not scan output folder: {e}")
    
    def _cross_reference_data(self):
        """Cross-reference logs, database, and output folder"""
        # Find missing videos (in DB but not in output folder)
        for video_id, info in self.db_videos.items():
            if video_id not in self.output_videos:
                if info['status'] == 'complete':
                    # This is bad - marked complete but files missing!
                    self.missing_videos.append({
                        'video_id': video_id,
                        'filename': info['filename'],
                        'status': info['status'],
                        'completed_at': info['completed_at'],
                        'severity': 'HIGH'  # Complete but files gone
                    })
        
        # Find orphaned videos (in output but not in DB)
        for video_id in self.output_videos:
            if video_id not in self.db_videos:
                self.orphaned_videos.append(video_id)
    
    def _process_line(self, line: str):
        """Process a single log line"""
        # Try to match log entry pattern
        match = self.log_pattern.match(line)
        
        if match:
            # New log entry
            timestamp, level, thread, module, message = match.groups()
            
            # Finalize any pending error with traceback
            if self.current_traceback and self.current_error:
                self._finalize_error()
            
            self.stats['total_entries'] += 1
            
            # Create entry
            entry = {
                'timestamp': timestamp,
                'level': level,
                'thread': thread.strip(),
                'module': module.strip(),
                'message': message.strip(),
                'traceback': []
            }
            
            # Categorize by level
            level_lower = level.lower()
            if level_lower == 'error':
                self.stats['errors'] += 1
                self.current_error = entry
                self.current_traceback = []
                self._categorize_error(entry)
            elif level_lower == 'warning':
                self.stats['warnings'] += 1
                self._categorize_warning(entry)
            elif level_lower == 'info':
                self.stats['info'] += 1
                self._categorize_info(entry)
            elif level_lower == 'debug':
                self.stats['debug'] += 1
            else:
                # Critical, etc.
                if level_lower == 'critical':
                    self.stats['crashes'] += 1
                    self.crashes.append(entry)
        
        else:
            # Continuation line (likely traceback)
            if self.current_traceback is not None:
                self.current_traceback.append(line)
    
    def _finalize_error(self):
        """Finalize error with collected traceback and extract metadata"""
        if self.current_error and self.current_traceback:
            self.current_error['traceback'] = self.current_traceback
            
            # Extract exception type
            exception_type = self._extract_exception_type(self.current_traceback)
            if exception_type:
                self.current_error['exception_type'] = exception_type
                self.exception_types[exception_type] += 1
            
            # NEW: Extract root cause from cascading exceptions
            root_cause, final_exc = self._extract_root_cause(self.current_traceback)
            if root_cause:
                self.current_error['root_cause'] = root_cause
                self.current_error['cascaded'] = True
                self.cascading_exceptions.append(self.current_error)
            
            # NEW: Extract video context
            video_id = self._extract_video_context(self.current_error)
            if video_id:
                self.current_error['video_id'] = video_id
                self.video_contexts[video_id] += 1
            
            # NEW: Compute hash for deduplication
            error_hash = self._compute_error_hash(self.current_error)
            self.current_error['error_hash'] = error_hash
            
            # NEW: Semantic categorization for AI
            category = self._categorize_error_semantically(self.current_error)
            self.current_error['category'] = category
            self.error_categories[category].append(self.current_error)
            
            # NEW: Operation type extraction
            operation = self._extract_operation_type(self.current_error)
            if operation:
                self.current_error['operation'] = operation
                self.operation_types[operation] += 1
            
            # NEW: Affected module tracking
            module_name = self.current_error['module'].split(':')[0].split('/')[-1]
            self.affected_modules[module_name] += 1
            
            # NEW: Time-based tracking
            date, day_name, hour = self._extract_time_components(self.current_error['timestamp'])
            self.current_error['date'] = date
            self.current_error['day_of_week'] = day_name
            self.current_error['hour'] = hour
            self.errors_by_hour[hour] += 1
            self.errors_by_day[date] += 1
            self.hourly_activity[hour]['errors'] += 1
            self.daily_summary[date]['errors'] += 1
            
            # NEW: Track error bursts (multiple errors in short time)
            if self.last_error_time:
                try:
                    current_time = datetime.strptime(self.current_error['timestamp'], '%Y-%m-%d %H:%M:%S')
                    time_diff = (current_time - self.last_error_time).total_seconds()
                    if time_diff < 5:  # Errors within 5 seconds = burst
                        self.current_error['burst'] = True
                    self.last_error_time = current_time
                except:
                    pass
            else:
                try:
                    self.last_error_time = datetime.strptime(self.current_error['timestamp'], '%Y-%m-%d %H:%M:%S')
                except:
                    pass
            
            # NEW: Extract file and line for quick navigation
            file_path, line_num = self._extract_file_and_line(self.current_error)
            if file_path:
                self.current_error['error_file'] = file_path
                self.current_error['error_line'] = line_num
            
            # NEW: Get AI fix suggestion from knowledge base
            fix_suggestion = self._get_fix_suggestion(self.current_error)
            if fix_suggestion:
                self.current_error['fix_suggestion'] = fix_suggestion
            
            # NEW: Only add unique errors (deduplication)
            if error_hash not in self.error_hashes:
                self.errors.append(self.current_error)
                self.error_hashes.add(error_hash)
            else:
                # Track duplicate count
                self.current_error['is_duplicate'] = True
        
        self.current_error = None
        self.current_traceback = None
    
    def _extract_exception_type(self, traceback: List[str]) -> Optional[str]:
        """Extract exception type from traceback"""
        for line in reversed(traceback):
            # Look for exception type (e.g., "FileNotFoundError:", "KeyError:")
            match = re.match(r'^([A-Za-z_][A-Za-z0-9_\.]*Error|[A-Za-z_][A-Za-z0-9_\.]*Exception):', line)
            if match:
                return match.group(1)
        return None
    
    def _extract_root_cause(self, traceback: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract root cause from cascading exceptions.
        Returns (first_exception, last_exception)
        """
        exceptions = []
        for line in traceback:
            match = re.match(r'^([A-Za-z_][A-Za-z0-9_\.]*Error|[A-Za-z_][A-Za-z0-9_\.]*Exception):', line)
            if match:
                exceptions.append(match.group(1))
        
        if exceptions:
            return (exceptions[0] if len(exceptions) > 1 else None, exceptions[-1])
        return (None, None)
    
    def _extract_video_context(self, entry: Dict) -> Optional[str]:
        """Extract video ID from error message or traceback"""
        text = entry['message'] + ' '.join(entry.get('traceback', []))
        
        # Patterns: web_XXXXX, output/XXXXX, upload_XXXXX
        patterns = [
            r'(web_[a-f0-9]{12})',
            r'(upload_[a-z0-9]+_\d+)',
            r'output[/\\\\]([a-f0-9]{12})',
            r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'  # UUID
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None
    
    def _compute_error_hash(self, entry: Dict) -> str:
        """Generate hash of error for deduplication"""
        # Hash based on exception type + first line of traceback + module
        key_parts = [
            entry.get('exception_type', 'Unknown'),
            entry['module'].split(':')[0],  # File without line number
        ]
        
        if entry.get('traceback'):
            # Get last non-empty traceback line (the actual exception)
            tb_lines = [line for line in entry['traceback'] if line.strip()]
            if tb_lines:
                key_parts.append(tb_lines[-1][:100])  # First 100 chars
        
        key = '|'.join(key_parts)
        return hashlib.md5(key.encode()).hexdigest()[:8]
    
    def _categorize_error_semantically(self, entry: Dict) -> str:
        """
        Categorize error into semantic groups for AI analysis.
        Returns category like: 'file_system', 'network', 'processing', etc.
        """
        message = entry['message'].lower()
        module = entry['module'].lower()
        exception = entry.get('exception_type', '').lower()
        
        # File system errors
        if any(x in exception for x in ['filenotfound', 'permission', 'ioerror']):
            return 'file_system'
        if any(x in message for x in ['no such file', 'cannot find file', 'access denied', 'permission']):
            return 'file_system'
        
        # Network/API errors
        if any(x in exception for x in ['connection', 'timeout', 'httperror']):
            return 'network'
        if any(x in message for x in ['connection', 'timeout', 'api', 'request failed']):
            return 'network'
        
        # Media processing errors
        if any(x in module for x in ['processor', 'whisper', 'diarization', 'audio']):
            return 'media_processing'
        if any(x in message for x in ['ffmpeg', 'transcription', 'audio', 'video', 'whisper']):
            return 'media_processing'
        
        # Model/AI errors
        if any(x in exception for x in ['runtimeerror']) and 'model' in message:
            return 'ai_model'
        if any(x in message for x in ['model', 'tensor', 'cuda', 'gpu', 'pytorch', 'shapes cannot be multiplied']):
            return 'ai_model'
        
        # Database errors
        if any(x in module for x in ['database', 'db']):
            return 'database'
        if any(x in message for x in ['database', 'sql', 'query']):
            return 'database'
        
        # Configuration/initialization errors
        if any(x in exception for x in ['nameerror', 'importerror', 'attributeerror']):
            return 'configuration'
        if any(x in message for x in ['not defined', 'import', 'missing', 'configuration']):
            return 'configuration'
        
        # Resource exhaustion
        if any(x in message for x in ['memory', 'out of memory', 'resource', 'disk space']):
            return 'resource_exhaustion'
        
        # Unknown/other
        return 'other'
    
    def _extract_operation_type(self, entry: Dict) -> Optional[str]:
        """Extract what operation was being performed when error occurred"""
        message = entry['message'].lower()
        module = entry['module'].lower()
        
        operations = {
            'transcription': ['transcription', 'whisper', 'speech to text'],
            'diarization': ['diarization', 'speaker', 'voiceprint'],
            'translation': ['translation', 'translate', 'nllb'],
            'audio_processing': ['audio processing', 'ffmpeg', 'audio conversion', 'extract_audio'],
            'video_download': ['download', 'yt-dlp', 'youtube', 'web video'],
            'export': ['export', 'generated', 'pdf', 'docx', 'srt', 'vtt'],
            'api_request': ['api/', 'endpoint', 'request'],
            'queue': ['queue', 'job', 'worker'],
            'initialization': ['initialized', 'startup', 'loading model'],
        }
        
        for op_type, keywords in operations.items():
            if any(kw in message or kw in module for kw in keywords):
                return op_type
        
        return None
    
    def _extract_time_components(self, timestamp_str: str) -> Tuple[str, str, int]:
        """
        Extract date, day of week, and hour from timestamp.
        Returns (date, day_name, hour)
        """
        try:
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            date = dt.strftime('%Y-%m-%d')
            day_name = dt.strftime('%A')
            hour = dt.hour
            return (date, day_name, hour)
        except:
            return ('unknown', 'unknown', 0)
    
    def _get_fix_suggestion(self, error: Dict) -> Optional[Dict]:
        """
        Match error to known fix suggestions from knowledge base.
        Returns fix dict or None if no match.
        """
        exception_type = error.get('exception_type', '')
        message = error.get('message', '').lower()
        traceback_text = ' '.join(error.get('traceback', [])).lower()
        
        if exception_type in self.FIX_SUGGESTIONS:
            fixes = self.FIX_SUGGESTIONS[exception_type]
            
            # Try to match specific error patterns
            for pattern, fix_info in fixes.items():
                if pattern.lower() in message or pattern.lower() in traceback_text:
                    return fix_info
        
        return None
    
    def _extract_file_and_line(self, error: Dict) -> Tuple[Optional[str], Optional[int]]:
        """
        Extract the exact file and line number where error occurred.
        Returns (file_path, line_number) for quick navigation.
        """
        traceback = error.get('traceback', [])
        
        # Look for file paths in traceback
        for line in reversed(traceback):
            # Match: File "path/to/file.py", line 123
            match = re.search(r'File "([^"]+)", line (\d+)', line)
            if match:
                file_path, line_num = match.groups()
                # Filter out system files, focus on our code
                if any(x in file_path for x in ['Video Transcriber', 'src/', 'scripts/']):
                    return (file_path, int(line_num))
        
        return (None, None)
    
    def _predict_next_failure(self) -> List[Dict]:
        """
        AI predictive analysis: Based on patterns, what might break next?
        """
        predictions = []
        
        # Check for resource exhaustion trajectory
        if self.resource_warnings:
            recent_warnings = self.resource_warnings[-20:]
            ram_values = []
            for w in recent_warnings:
                match = re.search(r'RAM (\d+\.?\d*)%', w['message'])
                if match:
                    ram_values.append(float(match.group(1)))
            
            if ram_values and len(ram_values) >= 5:
                # Check if RAM is trending upward
                if ram_values[-1] > 85 and ram_values[-1] > ram_values[0]:
                    predictions.append({
                        'type': 'resource_exhaustion',
                        'severity': 'HIGH',
                        'prediction': 'RAM usage trending upward - system may crash soon',
                        'current': f'{ram_values[-1]:.1f}%',
                        'action': 'Restart server or kill memory-heavy processes',
                        'file': 'src/services/resource_monitor.py'
                    })
        
        # Check for error frequency increase
        if self.errors_by_hour:
            recent_hours = sorted(self.errors_by_hour.items(), reverse=True)[:5]
            if recent_hours and any(count > 5 for _, count in recent_hours):
                predictions.append({
                    'type': 'error_storm',
                    'severity': 'MEDIUM',
                    'prediction': 'Error frequency increasing - system instability detected',
                    'current': f'{recent_hours[0][1]} errors in last hour',
                    'action': 'Review recent code changes, check for cascading failures',
                    'file': 'Check error categories for root cause'
                })
        
        # Check for recurring pattern
        if len(self.errors) > 5:
            categories = [e.get('category') for e in self.errors]
            most_common_category = Counter(categories).most_common(1)[0]
            if most_common_category[1] >= 3:
                predictions.append({
                    'type': 'recurring_issue',
                    'severity': 'MEDIUM',
                    'prediction': f'Recurring {most_common_category[0]} errors - needs permanent fix',
                    'current': f'{most_common_category[1]} occurrences',
                    'action': f'Implement proper fix for {most_common_category[0]} category',
                    'file': 'See error details in report'
                })
        
        return predictions
    
    def _categorize_error(self, entry: Dict):
        """Categorize error types"""
        message = entry['message'].lower()
        
        # Identify error types
        if 'failed' in message:
            self.error_types['Process Failed'] += 1
        if 'not found' in message or 'filenotfound' in message:
            self.error_types['File Not Found'] += 1
        if 'permission' in message or 'access denied' in message:
            self.error_types['Permission Error'] += 1
        if 'timeout' in message:
            self.error_types['Timeout'] += 1
        if 'connection' in message or 'network' in message:
            self.error_types['Network Error'] += 1
        if 'memory' in message or 'out of memory' in message:
            self.error_types['Memory Error'] += 1
        if 'database' in message or 'db' in message:
            self.error_types['Database Error'] += 1
        if 'model' in message and ('load' in message or 'not found' in message):
            self.error_types['Model Loading Error'] += 1
    
    def _categorize_warning(self, entry: Dict):
        """Categorize warnings"""
        message = entry['message'].lower()
        
        # Time-based tracking
        date, day_name, hour = self._extract_time_components(entry['timestamp'])
        entry['date'] = date
        entry['day_of_week'] = day_name
        entry['hour'] = hour
        self.warnings_by_hour[hour] += 1
        self.hourly_activity[hour]['warnings'] += 1
        self.daily_summary[date]['warnings'] += 1
        
        # Resource warnings
        if 'high resource usage' in message or 'cpu' in message or 'ram' in message:
            self.resource_warnings.append(entry)
        elif 'memory' in message:
            self.resource_warnings.append(entry)
        
        # Add to warnings list
        self.warnings.append(entry)
    
    def _categorize_info(self, entry: Dict):
        """Categorize important info events and extract API performance"""
        message = entry['message'].lower()
        
        # Time-based tracking
        date, day_name, hour = self._extract_time_components(entry['timestamp'])
        entry['date'] = date
        entry['day_of_week'] = day_name
        entry['hour'] = hour
        self.hourly_activity[hour]['requests'] += 1
        self.daily_summary[date]['info'] += 1
        
        # NEW: Extract API performance metrics (dur_ms)
        api_match = re.search(r'(GET|POST|PUT|DELETE)\s+([^\s]+)\s+status=(\d+)\s+dur_ms=(\d+)', entry['message'])
        if api_match:
            method, endpoint, status, dur_ms = api_match.groups()
            dur_ms_int = int(dur_ms)
            self.api_performance.append({
                'timestamp': entry['timestamp'],
                'method': method,
                'endpoint': endpoint,
                'status': int(status),
                'duration_ms': dur_ms_int,
                'date': date,
                'hour': hour
            })
            self.daily_summary[date]['api_calls'] += 1
            if dur_ms_int > 50:
                self.daily_summary[date]['slow_requests'] += 1
        
        # Track video processing completion
        if any(x in message for x in ['processing complete', 'transcript saved', 'generated:']):
            video_match = re.search(r'output[/\\\\]([a-zA-Z0-9_-]+)', entry['message'])
            if video_match:
                video_id = video_match.group(1)
                self.daily_summary[date]['videos_processed'].add(video_id)
        
        # Important events
        important_keywords = [
            'server started', 'server stopped', 'shutdown',
            'initialized', 'loaded model', 'downloaded',
            'processing complete', 'saved:', 'generated:',
            'queue', 'batch', 'cleanup'
        ]
        
        if any(keyword in message for keyword in important_keywords):
            self.important_events.append(entry)
    
    def generate_report(self, output_path: Optional[Path] = None, 
                       errors_only: bool = False,
                       include_tracebacks: bool = True) -> str:
        """
        Generate human-readable report
        
        Args:
            output_path: Optional path to save report
            errors_only: Only include errors/crashes
            include_tracebacks: Include full tracebacks in report
            
        Returns:
            Report string
        """
        lines = []
        
        # Header
        lines.append("=" * 80)
        lines.append("VIDEO TRANSCRIBER - LOG ANALYSIS REPORT")
        lines.append("=" * 80)
        lines.append(f"Log File: {self.log_path}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        lines.append("")
        
        # Statistics
        lines.append("📊 STATISTICS")
        lines.append("-" * 80)
        lines.append(f"Total Lines:        {self.stats['total_lines']:,}")
        lines.append(f"Total Log Entries:  {self.stats['total_entries']:,}")
        lines.append(f"  - Errors:         {self.stats['errors']:,}")
        lines.append(f"  - Warnings:       {self.stats['warnings']:,}")
        lines.append(f"  - Info:           {self.stats['info']:,}")
        lines.append(f"  - Debug:          {self.stats['debug']:,}")
        lines.append(f"  - Crashes:        {self.stats['crashes']:,}")
        lines.append("")
        
        # Time range
        if self.daily_summary:
            dates = sorted(self.daily_summary.keys())
            if dates:
                lines.append(f"Time Range:   {dates[0]} to {dates[-1]} ({len(dates)} days)")
                lines.append("")
        
        # AI ACTIONABLE SUMMARY (Top Priority)
        lines.append("🤖 AI ACTIONABLE SUMMARY")
        lines.append("=" * 80)
        lines.append("IMMEDIATE ACTIONS REQUIRED:")
        lines.append("")
        
        # Generate priority action items
        action_items = []
        action_num = 1
        
        # Check for data integrity issues (HIGHEST PRIORITY)
        if self.missing_videos:
            action_items.append(f"{action_num}. 🔴 CRITICAL: {len(self.missing_videos)} videos marked complete but FILES MISSING!")
            action_num += 1
        
        # Check for critical errors with fixes
        errors_with_fixes = [e for e in self.errors if e.get('fix_suggestion')]
        if errors_with_fixes:
            action_items.append(f"{action_num}. FIX {len(errors_with_fixes)} ERRORS WITH KNOWN SOLUTIONS (see detailed fixes below)")
            action_num += 1
        
        # Check for cascading failures
        if self.cascading_exceptions:
            action_items.append(f"{action_num}. ADDRESS ROOT CAUSES: {len(self.cascading_exceptions)} cascading exception chains found")
            action_num += 1
        
        # Check for high resource usage
        if self.resource_warnings:
            recent = self.resource_warnings[-1] if self.resource_warnings else None
            if recent:
                ram_match = re.search(r'RAM (\d+\.?\d*)%', recent['message'])
                if ram_match and float(ram_match.group(1)) > 85:
                    action_items.append(f"{action_num}. URGENT: RAM at {ram_match.group(1)}% - restart server or free memory")
                    action_num += 1
        
        # Check for orphaned videos
        if self.orphaned_videos:
            action_items.append(f"{action_num}. CLEANUP: {len(self.orphaned_videos)} orphaned video folders (not in database)")
            action_num += 1
        
        # Check for affected videos
        if self.video_contexts:
            action_items.append(f"{action_num}. INVESTIGATE: {len(self.video_contexts)} videos encountered errors during processing")
            action_num += 1
        
        if not action_items:
            lines.append("✅ No critical issues requiring immediate action")
        else:
            for item in action_items:
                lines.append(f"  {item}")
        
        lines.append("")
        lines.append("WHAT HAPPENED:")
        if self.errors:
            top_category = Counter([e.get('category', 'unknown') for e in self.errors]).most_common(1)[0]
            lines.append(f"  - Primary issue type: {top_category[0].replace('_', ' ').upper()} ({top_category[1]} errors)")
        if self.operation_types:
            top_op = self.operation_types.most_common(1)[0]
            lines.append(f"  - Most affected operation: {top_op[0].replace('_', ' ').title()} ({top_op[1]} failures)")
        if self.errors_by_hour:
            peak_hour = max(self.errors_by_hour.items(), key=lambda x: x[1])
            lines.append(f"  - Peak error time: {peak_hour[0]:02d}:00 ({peak_hour[1]} errors)")
        
        lines.append("")
        lines.append("=" * 80)
        lines.append("")
        
        # DATABASE & DATA INTEGRITY ANALYSIS
        if self.db_videos or self.output_videos:
            lines.append("💾 DATABASE & DATA INTEGRITY")
            lines.append("=" * 80)
            
            if self.db_videos:
                # Database statistics
                total_videos = len(self.db_videos)
                status_counts = Counter([v['status'] for v in self.db_videos.values()])
                
                lines.append(f"Database Videos: {total_videos}")
                for status, count in status_counts.most_common():
                    lines.append(f"  - {status}: {count}")
                lines.append("")
                
                # Success rate
                complete = status_counts.get('complete', 0)
                failed = status_counts.get('failed', 0)
                if total_videos > 0:
                    success_rate = (complete / total_videos) * 100
                    lines.append(f"Success Rate: {success_rate:.1f}% ({complete}/{total_videos})")
                    lines.append("")
            
            if self.output_videos:
                lines.append(f"Output Folder Videos: {len(self.output_videos)}")
                lines.append("")
            
            # Data integrity issues
            if self.missing_videos:
                lines.append("🔴 CRITICAL DATA INTEGRITY ISSUES:")
                lines.append(f"   {len(self.missing_videos)} videos marked COMPLETE but output files MISSING!")
                lines.append("")
                lines.append("   Missing Videos:")
                for video in self.missing_videos[:10]:  # Show first 10
                    lines.append(f"     - {video['video_id']}: {video['filename']}")
                    lines.append(f"       Completed: {video['completed_at']}")
                if len(self.missing_videos) > 10:
                    lines.append(f"     ... and {len(self.missing_videos) - 10} more")
                lines.append("")
                lines.append("   🤖 AI RECOMMENDATION:")
                lines.append("      - These videos need reprocessing OR database cleanup")
                lines.append("      - Check disk space and file permissions")
                lines.append("      - Verify backup/restore processes")
                lines.append("")
            
            if self.orphaned_videos:
                lines.append(f"⚠️  ORPHANED VIDEO FOLDERS: {len(self.orphaned_videos)}")
                lines.append("   Folders exist in output/ but not in database")
                lines.append("")
                for video_id in self.orphaned_videos[:10]:
                    lines.append(f"     - {video_id}")
                if len(self.orphaned_videos) > 10:
                    lines.append(f"     ... and {len(self.orphaned_videos) - 10} more")
                lines.append("")
                lines.append("   🤖 AI RECOMMENDATION:")
                lines.append("      - Safe to delete these folders OR re-import to database")
                lines.append("")
            
            if self.db_videos:
                # Recent failures from database
                recent_failures = [v for v in self.db_videos.values() if v['status'] == 'failed']
                if recent_failures:
                    lines.append(f"📉 RECENT FAILURES FROM DATABASE: {len(recent_failures)}")
                    lines.append("")
                    for video in recent_failures[:5]:
                        lines.append(f"   - {video['video_id']}: {video['filename']}")
                        if video['error_message']:
                            lines.append(f"     Error: {video['error_message'][:80]}...")
                    lines.append("")
            
            lines.append("=" * 80)
            lines.append("")
        
        # AI PREDICTIVE ANALYSIS
        predictions = self._predict_next_failure()
        if predictions:
            lines.append("🔮 PREDICTIVE ANALYSIS (AI)")
            lines.append("=" * 80)
            lines.append("POTENTIAL FUTURE FAILURES:")
            lines.append("")
            
            for pred in predictions:
                severity_icon = "🔴" if pred['severity'] == 'HIGH' else "🟡"
                lines.append(f"{severity_icon} {pred['severity']}: {pred['prediction']}")
                lines.append(f"   Current: {pred['current']}")
                lines.append(f"   Action: {pred['action']}")
                lines.append(f"   Check: {pred['file']}")
                lines.append("")
            
            lines.append("=" * 80)
            lines.append("")
        
        # Error types summary
        if self.error_types:
            lines.append("🔴 ERROR TYPES")
            lines.append("-" * 80)
            for error_type, count in self.error_types.most_common():
                lines.append(f"  {error_type:30s} {count:,} occurrences")
            lines.append("")
        
        # Exception types summary
        if self.exception_types:
            lines.append("⚠️  EXCEPTION TYPES")
            lines.append("-" * 80)
            for exc_type, count in self.exception_types.most_common():
                lines.append(f"  {exc_type:30s} {count:,} occurrences")
            lines.append("")
        
        # NEW: Daily activity summary
        if self.daily_summary:
            lines.append("📅 DAILY SUMMARY (AI Analysis)")
            lines.append("-" * 80)
            for date in sorted(self.daily_summary.keys()):
                data = self.daily_summary[date]
                videos_count = len(data['videos_processed'])
                lines.append(f"{date}:")
                lines.append(f"  Errors: {data['errors']}, Warnings: {data['warnings']}, API Calls: {data['api_calls']}")
                lines.append(f"  Slow Requests: {data['slow_requests']}, Videos Processed: {videos_count}")
            lines.append("")
        
        # NEW: Hourly error patterns
        if self.errors_by_hour:
            lines.append("⏰ HOURLY ERROR PATTERNS")
            lines.append("-" * 80)
            lines.append("Hour | Errors | Warnings | Requests | Pattern")
            lines.append("-----|--------|----------|----------|--------")
            for hour in range(24):
                err_count = self.errors_by_hour.get(hour, 0)
                warn_count = self.warnings_by_hour.get(hour, 0)
                req_count = self.hourly_activity[hour]['requests']
                
                # Determine pattern
                if err_count > 10:
                    pattern = "🔴 HIGH ERRORS"
                elif err_count > 5:
                    pattern = "⚠️  Elevated"
                elif req_count > 500:
                    pattern = "📈 High Activity"
                else:
                    pattern = "✅ Normal"
                
                lines.append(f" {hour:02d}  |  {err_count:4d}  |  {warn_count:6d}  |  {req_count:6d}   | {pattern}")
            lines.append("")
        
        # NEW: Error categories (AI semantic grouping)
        if self.error_categories:
            lines.append("🏷️  ERROR CATEGORIES (AI Semantic Analysis)")
            lines.append("-" * 80)
            for category, errors in sorted(self.error_categories.items(), key=lambda x: len(x[1]), reverse=True):
                if not errors:
                    continue
                lines.append(f"  {category.upper().replace('_', ' ')}:")
                lines.append(f"    Count: {len(errors)}")
                # Show example error
                if errors:
                    example = errors[0]
                    lines.append(f"    Example: {example['message'][:60]}...")
                lines.append("")
        
        # NEW: Operation types
        if self.operation_types:
            lines.append("🔧 OPERATIONS WITH ERRORS")
            lines.append("-" * 80)
            for op_type, count in self.operation_types.most_common():
                lines.append(f"  {op_type.replace('_', ' ').title():30s} {count:,} error(s)")
            lines.append("")
        
        # NEW: Affected modules
        if self.affected_modules:
            lines.append("📦 AFFECTED MODULES")
            lines.append("-" * 80)
            for module, count in self.affected_modules.most_common(10):
                lines.append(f"  {module:40s} {count:,} error(s)")
            lines.append("")
        
        # NEW: Cascading exceptions summary
        if self.cascading_exceptions:
            lines.append("🔗 CASCADING EXCEPTIONS (Root Causes)")
            lines.append("-" * 80)
            lines.append(f"Found {len(self.cascading_exceptions)} cascading exception chains")
            lines.append("")
            for exc in self.cascading_exceptions[:5]:  # Show top 5
                lines.append(f"  [{exc['timestamp']}] Root: {exc.get('root_cause', 'Unknown')} → {exc.get('exception_type', 'Unknown')}")
                lines.append(f"    {exc['message'][:80]}...")
            lines.append("")
        
        # NEW: Video contexts with errors
        if self.video_contexts:
            lines.append("🎬 VIDEOS WITH ERRORS")
            lines.append("-" * 80)
            lines.append(f"Total affected videos: {len(self.video_contexts)}")
            lines.append("")
            for video_id, count in self.video_contexts.most_common(10):
                lines.append(f"  {video_id:40s} {count:,} error(s)")
            lines.append("")
        
        # NEW: API performance summary
        if self.api_performance:
            lines.append("⚡ API PERFORMANCE")
            lines.append("-" * 80)
            total_requests = len(self.api_performance)
            avg_duration = sum(r['duration_ms'] for r in self.api_performance) / total_requests
            slow_requests = [r for r in self.api_performance if r['duration_ms'] > 50]
            
            lines.append(f"Total API Requests: {total_requests:,}")
            lines.append(f"Average Duration:   {avg_duration:.1f} ms")
            lines.append(f"Slow Requests (>50ms): {len(slow_requests):,}")
            lines.append("")
            
            if slow_requests:
                lines.append("  Slowest endpoints:")
                endpoint_times = defaultdict(list)
                for r in self.api_performance:
                    endpoint_times[r['endpoint']].append(r['duration_ms'])
                
                for endpoint, times in sorted(endpoint_times.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)[:5]:
                    avg_time = sum(times) / len(times)
                    lines.append(f"    {endpoint:50s} {avg_time:.1f} ms avg ({len(times)} calls)")
                lines.append("")
        
        # Crashes (Critical)
        if self.crashes:
            lines.append("💥 CRASHES / CRITICAL ERRORS")
            lines.append("-" * 80)
            for crash in self.crashes:
                lines.append(f"[{crash['timestamp']}] {crash['module']}")
                lines.append(f"  Message: {crash['message']}")
                if include_tracebacks and crash.get('traceback'):
                    lines.append("  Traceback:")
                    for tb_line in crash['traceback'][:20]:  # Limit to 20 lines
                        lines.append(f"    {tb_line}")
                lines.append("")
        
        # Errors
        if self.errors:
            lines.append("❌ ERRORS (Deduplicated)")
            lines.append("-" * 80)
            lines.append(f"Total Unique: {len(self.errors)} errors")
            lines.append(f"Duplicates Removed: {len(self.error_hashes) - len(self.errors)}")
            lines.append("")
            
            # Group by exception type
            errors_by_type: Dict[str, List[Dict]] = defaultdict(list)
            for error in self.errors:
                exc_type = error.get('exception_type', 'Unknown')
                errors_by_type[exc_type].append(error)
            
            for exc_type, error_list in sorted(errors_by_type.items(), 
                                              key=lambda x: len(x[1]), 
                                              reverse=True):
                lines.append(f"  {exc_type}: {len(error_list)} unique occurrence(s)")
                
                # Show first 3 examples
                for i, error in enumerate(error_list[:3]):
                    lines.append(f"    [{error['timestamp']}] {error['module']}")
                    lines.append(f"      {error['message']}")
                    
                    # NEW: Show video context and cascading info
                    if error.get('video_id'):
                        lines.append(f"      📹 Video: {error['video_id']}")
                    if error.get('cascaded'):
                        lines.append(f"      🔗 Root cause: {error.get('root_cause')}")
                    if error.get('burst'):
                        lines.append(f"      ⚠️  Part of error burst")
                    
                    # AI ASSISTANT: File and line for quick navigation
                    if error.get('error_file'):
                        lines.append(f"      📂 Location: {error['error_file']}:{error.get('error_line', '?')}")
                    
                    # AI ASSISTANT: Fix suggestion from knowledge base
                    if error.get('fix_suggestion'):
                        fix = error['fix_suggestion']
                        lines.append(f"      ")
                        lines.append(f"      🤖 AI FIX SUGGESTION:")
                        lines.append(f"         Diagnosis: {fix['diagnosis']}")
                        lines.append(f"         Fix: {fix['fix']}")
                        lines.append(f"         Prevention: {fix['prevention']}")
                    
                    if include_tracebacks and error.get('traceback'):
                        # Show last 5 lines of traceback (most relevant)
                        tb_lines = [line for line in error['traceback'] if line.strip()]
                        if tb_lines:
                            lines.append("      Traceback (last 5 lines):")
                            for tb_line in tb_lines[-5:]:
                                lines.append(f"        {tb_line}")
                    lines.append("")
                
                if len(error_list) > 3:
                    lines.append(f"    ... and {len(error_list) - 3} more")
                    lines.append("")
        
        if not errors_only:
            # Resource warnings
            if self.resource_warnings:
                lines.append("⚡ RESOURCE WARNINGS")
                lines.append("-" * 80)
                lines.append(f"Total: {len(self.resource_warnings)} warnings")
                lines.append("")
                
                # Show last 10
                for warning in self.resource_warnings[-10:]:
                    lines.append(f"[{warning['timestamp']}] {warning['message']}")
                lines.append("")
            
            # Other warnings
            other_warnings = [w for w in self.warnings if w not in self.resource_warnings]
            if other_warnings:
                lines.append("⚠️  OTHER WARNINGS")
                lines.append("-" * 80)
                lines.append(f"Total: {len(other_warnings)} warnings")
                lines.append("")
                
                # Group similar warnings
                warning_counts: Counter = Counter()
                for warning in other_warnings:
                    # Use first 50 chars as key
                    key = warning['message'][:50]
                    warning_counts[key] += 1
                
                for msg_prefix, count in warning_counts.most_common(10):
                    lines.append(f"  [{count}x] {msg_prefix}...")
                lines.append("")
            
            # Important events
            if self.important_events:
                lines.append("ℹ️  IMPORTANT EVENTS")
                lines.append("-" * 80)
                lines.append(f"Total: {len(self.important_events)} events")
                lines.append("")
                
                # Show last 20
                for event in self.important_events[-20:]:
                    lines.append(f"[{event['timestamp']}] {event['message']}")
                lines.append("")
        
        # Footer
        lines.append("=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)
        
        report = "\n".join(lines)
        
        # Save to file if requested
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"✓ Report saved to: {output_path}")
        
        return report
    
    def export_json(self, output_path: Path):
        """
        Export analysis in JSON format for AI parsing.
        Includes all data in structured, machine-readable format.
        """
        # Convert sets to lists for JSON serialization
        for date in self.daily_summary:
            self.daily_summary[date]['videos_processed'] = list(self.daily_summary[date]['videos_processed'])
        
        data = {
            'metadata': {
                'log_file': str(self.log_path),
                'analyzed_at': datetime.now().isoformat(),
                'analyzer_version': '3.0',
            },
            'statistics': self.stats,
            'time_range': {
                'dates': sorted(self.daily_summary.keys()) if self.daily_summary else [],
                'days_covered': len(self.daily_summary)
            },
            'actionable_summary': {
                'errors_with_fixes': len([e for e in self.errors if e.get('fix_suggestion')]),
                'cascading_exceptions': len(self.cascading_exceptions),
                'affected_videos': len(self.video_contexts),
                'priority_actions': []
            },
            'predictions': self._predict_next_failure(),
            'errors': {
                'unique_count': len(self.errors),
                'duplicates_removed': len(self.error_hashes) - len(self.errors),
                'by_type': dict(self.exception_types),
                'by_category': {cat: len(errs) for cat, errs in self.error_categories.items()},
                'by_operation': dict(self.operation_types),
                'details': self.errors[:50]  # First 50 errors
            },
            'time_analysis': {
                'errors_by_hour': dict(self.errors_by_hour),
                'errors_by_day': dict(self.errors_by_day),
                'warnings_by_hour': dict(self.warnings_by_hour),
                'daily_summary': dict(self.daily_summary),
            },
            'performance': {
                'api_calls': len(self.api_performance),
                'avg_response_time_ms': sum(r['duration_ms'] for r in self.api_performance) / len(self.api_performance) if self.api_performance else 0,
                'slow_requests': len([r for r in self.api_performance if r['duration_ms'] > 50]),
                'slowest_endpoints': []
            },
            'affected_resources': {
                'videos': dict(self.video_contexts),
                'modules': dict(self.affected_modules.most_common(20)),
            },
            'warnings': {
                'total': len(self.warnings),
                'resource_warnings': len(self.resource_warnings),
                'recent_samples': self.warnings[-10:]
            },
            'database': {
                'total_videos': len(self.db_videos),
                'status_counts': dict(Counter([v['status'] for v in self.db_videos.values()])),
                'success_rate': (sum(1 for v in self.db_videos.values() if v['status'] == 'complete') / len(self.db_videos) * 100) if self.db_videos else 0
            },
            'data_integrity': {
                'missing_videos': self.missing_videos,
                'orphaned_videos': self.orphaned_videos,
                'output_folder_count': len(self.output_videos)
            }
        }
        
        # Add slowest API endpoints
        if self.api_performance:
            endpoint_times = defaultdict(list)
            for r in self.api_performance:
                endpoint_times[r['endpoint']].append(r['duration_ms'])
            
            data['performance']['slowest_endpoints'] = [
                {
                    'endpoint': endpoint,
                    'avg_ms': sum(times) / len(times),
                    'calls': len(times)
                }
                for endpoint, times in sorted(endpoint_times.items(), 
                                            key=lambda x: sum(x[1])/len(x[1]), 
                                            reverse=True)[:10]
            ]
        
        # Write JSON
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"✓ JSON export saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze Video Transcriber server logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze default log file
  python scripts/analyze_logs.py
  
  # Analyze specific log file
  python scripts/analyze_logs.py --log-file logs/custom.log
  
  # Save report to file
  python scripts/analyze_logs.py --output logs/analysis_report.txt
  
  # Show only errors and crashes
  python scripts/analyze_logs.py --errors-only
  
  # Exclude tracebacks for cleaner output
  python scripts/analyze_logs.py --no-tracebacks
        """
    )
    
    parser.add_argument(
        '--log-file',
        type=Path,
        default=Path('logs/server.log'),
        help='Path to log file (default: logs/server.log)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=Path,
        help='Save report to file'
    )
    
    parser.add_argument(
        '--errors-only',
        action='store_true',
        help='Show only errors and crashes'
    )
    
    parser.add_argument(
        '--no-tracebacks',
        action='store_true',
        help='Exclude tracebacks from report'
    )
    
    parser.add_argument(
        '--json',
        type=Path,
        help='Export analysis in JSON format for AI parsing'
    )
    
    parser.add_argument(
        '--no-rotated',
        action='store_true',
        help='Skip rotated log files (only analyze main log)'
    )
    
    parser.add_argument(
        '--db',
        type=Path,
        default=Path('processed.db'),
        help='Path to database file (default: processed.db)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('output'),
        help='Path to output folder (default: output)'
    )
    
    args = parser.parse_args()
    
    try:
        # Create analyzer with all data sources
        analyzer = LogAnalyzer(
            log_path=args.log_file,
            include_rotated=not args.no_rotated,
            db_path=args.db,
            output_dir=args.output_dir
        )
        
        # Analyze log
        analyzer.analyze()
        
        # Export JSON if requested
        if args.json:
            analyzer.export_json(args.json)
        
        # Generate report
        report = analyzer.generate_report(
            output_path=args.output,
            errors_only=args.errors_only,
            include_tracebacks=not args.no_tracebacks
        )
        
        # Print to console if no output file
        if not args.output:
            print("\n" + report)
        
        # Print AI debug instructions with COT loop
        print("\n" + "=" * 80)
        print("🤖 AI DEBUGGING WORKFLOW - CHAIN OF THOUGHT (COT) LOOP")
        print("=" * 80)
        print("\n📋 COPY & PASTE THIS TO YOUR AI ASSISTANT:")
        print("-" * 80)
        print("""
I need you to systematically debug ALL issues using a Chain of Thought loop.

**Analysis Files:**
- Report: logs/holistic_analysis.txt
- JSON: logs/holistic_analysis.json

**COT LOOP - Execute this process iteratively:**

═══════════════════════════════════════════════════════════════════
ITERATION START - Think step-by-step through each phase:
═══════════════════════════════════════════════════════════════════

📖 PHASE 1: ANALYZE (Chain of Thought)
─────────────────────────────────────
Think through:
1. Read logs/holistic_analysis.txt completely
2. What does "AI ACTIONABLE SUMMARY" say?
3. How many critical issues exist?
4. What are the priority levels? (Critical → High → Medium)
5. Which issues have AI fix suggestions?
6. What are the root causes vs symptoms?

Output your thinking:
"I've analyzed the report. Here's my understanding:
 - Total issues: X
 - Critical: Y (list them)
 - Root causes identified: Z
 - Top 3 priorities are: ..."

🎯 PHASE 2: PRIORITIZE (Chain of Thought)
──────────────────────────────────────
Think through:
1. Which issue will have the biggest impact if fixed?
2. Are there cascading failures? (Fix root cause first)
3. Can fixing one issue solve multiple problems?
4. Which fixes are low-risk vs high-risk?
5. Do I have enough context to fix this?

Output your reasoning:
"I'll start with issue X because:
 - It's the root cause of Y other errors
 - It has a known fix suggestion
 - Risk level is low
 - Impact is high"

🔧 PHASE 3: PLAN FIX (Chain of Thought)
───────────────────────────────────────
Think through:
1. What exactly is the problem? (State it clearly)
2. What does the AI fix suggestion recommend?
3. What file and line needs to change?
4. What validation should I add to prevent recurrence?
5. What could go wrong with this fix?
6. What should I test after the fix?

Output your plan:
"For issue X, here's my fix plan:
 - Problem: [clear statement]
 - Location: file.py:line
 - Change: [specific code change]
 - Prevention: [validation to add]
 - Test: [how to verify]"

✍️ PHASE 4: IMPLEMENT (Chain of Thought)
─────────────────────────────────────────
Think through:
1. Am I making the minimal necessary change?
2. Am I following the AI suggestion's prevention advice?
3. Am I adding proper error handling?
4. Am I documenting why this change is needed?
5. Have I considered edge cases?

Output your implementation:
"Implementing fix for issue X:
 [make the code change]
 
 What I changed and why:
 - Added [X] because [reason]
 - This prevents [Y] from happening
 - Edge cases handled: [Z]"

🧪 PHASE 5: VERIFY (Chain of Thought)
──────────────────────────────────────
Think through:
1. What specific test confirms this is fixed?
2. What would indicate the fix didn't work?
3. Could this fix cause new issues?
4. Should I check related code?

Output verification steps:
"To verify this fix works:
 1. [specific test step]
 2. [what to observe]
 3. [success criteria]
 
 USER: Please run these tests and report results."

⏸️  WAIT FOR USER CONFIRMATION
    (Don't proceed until user confirms test results)

📊 PHASE 6: EVALUATE (Chain of Thought)
────────────────────────────────────────
After user confirms test:

Think through:
1. Did the fix work? (Yes/No/Partially)
2. Did it introduce new issues?
3. How many issues remain?
4. Should I adjust my approach?
5. What did I learn for the next fix?

Output your evaluation:
"Test results show: [success/failure]
 - If success: Moving to next issue
 - If failure: Here's my alternative approach: [explain]
 
 Remaining issues: X
 Next priority: [issue Y]"

═══════════════════════════════════════════════════════════════════
ITERATION END - Repeat loop until "✅ No critical issues"
═══════════════════════════════════════════════════════════════════

After each iteration, I'll rerun:
python scripts/analyze_logs.py --output logs/holistic_analysis.txt

Then paste this prompt again to start the next COT loop iteration.

🎯 CRITICAL RULES:
- Think out loud through EVERY phase
- Never skip the "think through" steps
- Always wait for user test confirmation
- One issue at a time, no shortcuts
- Learn from each iteration

Ready? Begin PHASE 1: ANALYZE by reading the report and thinking through your understanding.
        """)
        print("-" * 80)
        print("\n💡 TIP: This COT loop ensures systematic, thoughtful debugging")
        print("=" * 80)
    
    except Exception as e:
        print(f"❌ Error analyzing log: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
