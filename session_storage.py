"""
Session Storage System - Stores navigation outcomes to learn and improve over time
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


class SessionStorage:
    """Store and retrieve navigation session outcomes for learning"""
    
    def __init__(self, storage_file: str = "navigation_sessions.json"):
        self.storage_file = storage_file
        self.sessions = self._load_sessions()
    
    def _load_sessions(self) -> List[Dict]:
        """Load existing sessions from file"""
        if not os.path.exists(self.storage_file):
            return []
        
        try:
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[SessionStorage] Error loading sessions: {e}")
            return []
    
    def _save_sessions(self):
        """Save sessions to file"""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.sessions, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[SessionStorage] Error saving sessions: {e}")
            return False
    
    def save_session(self, session_data: Dict):
        """
        Save a navigation session with outcome
        
        session_data should contain:
        - start_url: str
        - user_intent: str
        - final_url: str
        - success: bool
        - steps_taken: List[Dict] (each step with: url, action, element_clicked, timestamp)
        - form_found: bool
        - form_filled: bool
        - fields_filled_count: int
        - error: Optional[str]
        - timestamp: str
        """
        session_data['timestamp'] = datetime.now().isoformat()
        session_data['session_id'] = f"{session_data.get('user_intent', 'unknown')}_{int(datetime.now().timestamp())}"
        
        self.sessions.append(session_data)
        self.deduplicate_sessions()
        self._save_sessions()
        print(f"[SessionStorage] ✅ Saved and deduplicated session: {session_data['session_id']}")
    
    def _get_path_signature(self, session: Dict) -> str:
        """Create a unique signature for a navigation path"""
        start_url = session.get('start_url', '')
        intent = session.get('user_intent', '')
        steps = session.get('steps_taken', [])
        
        # Path is defined by the sequence of URLs visited
        path_urls = [step.get('url', '') for step in steps if step.get('url')]
        path_string = "->".join(path_urls)
        
        return f"{start_url}|{intent}|{path_string}"

    def deduplicate_sessions(self):
        """Remove redundant sessions, keeping the best/most recent ones"""
        if not self.sessions:
            return
            
        unique_sessions = {}
        
        # Sort sessions by timestamp ascending so later ones overwrite earlier ones
        # and successful ones are preferred
        sorted_sessions = sorted(
            self.sessions, 
            key=lambda x: (x.get('timestamp', ''), x.get('success', False))
        )
        
        for session in sorted_sessions:
            sig = self._get_path_signature(session)
            
            # If we already have this path, prioritize success
            if sig in unique_sessions:
                existing = unique_sessions[sig]
                if session.get('success') and not existing.get('success'):
                    unique_sessions[sig] = session
                elif session.get('success') == existing.get('success'):
                    # Both same success status, keep the one with more fields filled or more recent
                    if session.get('fields_filled_count', 0) >= existing.get('fields_filled_count', 0):
                        unique_sessions[sig] = session
            else:
                unique_sessions[sig] = session
        
        original_count = len(self.sessions)
        self.sessions = list(unique_sessions.values())
        new_count = len(self.sessions)
        
        if original_count != new_count:
            print(f"[SessionStorage] Deduplicated: {original_count} -> {new_count} sessions")
    
    def get_successful_paths(self, start_url: str, user_intent: str) -> List[Dict]:
        """Get successful navigation paths for similar intents"""
        similar_sessions = []
        
        for session in self.sessions:
            # Check if session is successful and similar
            if session.get('success') and session.get('form_found'):
                # Match by start URL or similar intent
                if start_url in session.get('start_url', '') or session.get('start_url', '') in start_url:
                    similar_sessions.append(session)
                elif self._intent_similarity(user_intent, session.get('user_intent', '')) > 0.5:
                    similar_sessions.append(session)
        
        # Sort by most recent first
        similar_sessions.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return similar_sessions
    
    def _intent_similarity(self, intent1: str, intent2: str) -> float:
        """Calculate similarity between two intents (simple word overlap)"""
        words1 = set(intent1.lower().split())
        words2 = set(intent2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def get_known_form_urls(self) -> Dict[str, str]:
        """Get all known form URLs that were successfully reached"""
        form_urls = {}
        
        for session in self.sessions:
            if session.get('success') and session.get('form_found'):
                intent = session.get('user_intent', 'unknown')
                final_url = session.get('final_url', '')
                if final_url:
                    form_urls[intent] = final_url
        
        return form_urls
    
    def get_login_pages(self) -> List[str]:
        """Get all known login page URLs"""
        login_urls = set()
        
        for session in self.sessions:
            steps = session.get('steps_taken', [])
            for step in steps:
                if step.get('is_login_page'):
                    login_urls.add(step.get('url', ''))
        
        return list(login_urls)
    
    def clear_old_sessions(self, days: int = 30):
        """Clear sessions older than specified days"""
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(days=days)
        
        original_count = len(self.sessions)
        self.sessions = [
            s for s in self.sessions 
            if datetime.fromisoformat(s.get('timestamp', '1970-01-01')) > cutoff
        ]
        
        removed = original_count - len(self.sessions)
        if removed > 0:
            self._save_sessions()
            print(f"[SessionStorage] Cleared {removed} old sessions")
        
        return removed
