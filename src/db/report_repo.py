"""
report_repo.py — Universal PLC Monitor
Retrieves aggregated data for production reports and analytics.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List

from .database import Database

logger = logging.getLogger(__name__)


class ReportRepository:
    """
    Repository for generating production reports.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_sessions_summary(self, model_id: int = None, date_from: str = None, date_to: str = None,
                             session_id: int = None, limit: int = None) -> List[Dict[str, Any]]:
        """
        Unified summary method for ReportsPage.
        Calculates pass_rate_pct on the fly.
        """
        query = """
            SELECT s.id as session_id, s.started_at, s.ended_at, 
                   s.ok_count, s.ng_count, s.batch_count, s.overall_result,
                   m.name as model_name, u.username as operator_name,
                   u.username as operator_username,
                   CASE WHEN (s.ended_at IS NOT NULL AND s.started_at IS NOT NULL)
                        THEN CAST((julianday(s.ended_at) - julianday(s.started_at)) * 86400.0 AS REAL)
                        ELSE 0 END as duration_sec,
                   CASE WHEN (s.ok_count + s.ng_count) > 0 
                        THEN CAST(s.ok_count AS FLOAT) / (s.ok_count + s.ng_count) * 100 
                        ELSE 0 END as pass_rate_pct
            FROM test_sessions s
            JOIN models m ON s.model_id = m.id
            JOIN users u ON s.operator_id = u.id
        """
        clauses = []
        params = []
        
        if session_id:
            clauses.append("s.id = ?")
            params.append(session_id)
        if model_id:
            clauses.append("s.model_id = ?")
            params.append(model_id)
        if date_from:
            clauses.append("date(s.started_at) >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("date(s.started_at) <= ?")
            params.append(date_to)
            
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
            
        query += " ORDER BY s.started_at DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        return self.db.fetchall(query, tuple(params))

    def get_session_detail(self, session_id: int) -> Dict[str, Any]:
        """
        Returns full session details including results and comments.
        Matches ReportsPage expectations.
        """
        session = self.db.fetchone("""
            SELECT s.*, m.name as model_name, u.username as operator_name
            FROM test_sessions s
            JOIN models m ON s.model_id = m.id
            JOIN users u ON s.operator_id = u.id
            WHERE s.id = ?
        """, (session_id,))
        if not session: return {}
        
        results = self.db.fetchall("""
            SELECT tr.*, lib.unit as unit
            FROM test_results tr
            LEFT JOIN register_library lib ON tr.register_id = lib.id
            WHERE tr.session_id = ?
        """, (session_id,))
        
        # Group results by group_name (module)
        grouped_results = {}
        for r in results:
            grp = r["group_name"] or "General"
            if grp not in grouped_results:
                grouped_results[grp] = []
            
            r_dict = dict(r)
            r_dict["param_name"] = r["display_name"]
            grouped_results[grp].append(r_dict)
            
        comments = self.db.fetchall("""
            SELECT c.*, u.username 
            FROM session_comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.session_id = ?
        """, (session_id,))
        
        return {
            "session": session,
            "results": grouped_results,
            "comments": comments,
            "alarms": [] # Not implemented in v4.0 yet
        }

    def get_all_results_for_range(self, model_id: int = None, date_from: str = None,
                                   date_to: str = None) -> List[Dict[str, Any]]:
        """
        Returns every test_result row across all sessions in the date range,
        enriched with session date, time, and operator name.
        Powers both the in-UI bulk table and the bulk export.
        """
        query = """
            SELECT
                s.id as session_id,
                s.started_at,
                s.overall_result as session_result,
                u.username as operator_name,
                m.name as model_name,
                r.group_name,
                r.display_name,
                r.measured_value,
                r.raw_value,
                r.result,
                r.limit_min,
                r.limit_max,
                lib.unit as unit
            FROM test_results r
            JOIN test_sessions s ON r.session_id = s.id
            JOIN users u ON s.operator_id = u.id
            JOIN models m ON s.model_id = m.id
            LEFT JOIN register_library lib ON r.register_id = lib.id
        """
        clauses = []
        params = []

        if model_id:
            clauses.append("s.model_id = ?")
            params.append(model_id)
        if date_from:
            clauses.append("date(s.started_at) >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("date(s.started_at) <= ?")
            params.append(date_to)

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY s.started_at, r.group_name, r.display_name"
        return self.db.fetchall(query, tuple(params))
