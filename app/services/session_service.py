from datetime import datetime
from random import random
from typing import Optional, List, Dict

from sqlalchemy.orm import Session as DBSession

from app.db.session import get_db
from app.db.models import StudySession, Lesson, DifficultyLevel, lesson_knowledge, PracticeResult
from app.schemas.session import StudySessionCreate, QuestionItem, PracticeResultCreate, MasteryReport
from fastapi import HTTPException, Depends, status


class SessionService:
    """Service for Study Sessions, Practice Results, and Mastery Analysis"""

    def __init__(self, db: DBSession):
        self.db = db

    # ============================================
    # STUDY SESSION
    # ============================================

    def create_session(self, user_id: int, data: StudySessionCreate) -> StudySession:
        """Create a new study session for a user"""
        # Validate lessons exist
        existing_ids = [
            r[0] for r in
            self.db.query(Lesson.id).filter(Lesson.id.in_(data.selectedLessons)).all()
        ]
        missing = set(data.selectedLessons) - set(existing_ids)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lessons not found: {sorted(missing)}"
            )

        session = StudySession(
            user_id=user_id,
            grade=data.grade,
            selected_lessons=data.selectedLessons,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session_by_id(self, session_id: int) -> Optional[StudySession]:
        return self.db.query(StudySession).filter(StudySession.id == session_id).first()

    def get_sessions_for_user(
            self,
            user_id: int,
            skip: int = 0,
            limit: int = 50,
    ) -> List[StudySession]:
        return (
            self.db.query(StudySession)
            .filter(StudySession.user_id == user_id)
            .order_by(StudySession.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def complete_session(self, session_id: int, user_id: int) -> StudySession:
        """Mark a session as completed"""
        session = self.get_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your session")
        if session.completed_at:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session already completed")

        session.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(session)
        return session

    def delete_session(self, session_id: int) -> None:
        session = self.get_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        self.db.delete(session)
        self.db.commit()

    # ============================================
    # QUESTION SELECTION (Weighted Sampling)
    # ============================================

    def select_questions(
            self,
            lesson_ids: List[int],
            num_questions: int = 10,
            difficulty: Optional[DifficultyLevel] = None,
    ) -> List[QuestionItem]:
        """
        Weighted sampling of questions from knowledge nodes linked to lessons.

        Weight = node.importance_weight (1-10 scale)
        Higher importance → more likely to be sampled.
        """
        from app.db.models.knowledge import KnowledgeNode

        # Get all nodes linked to the lessons
        nodes: List[KnowledgeNode] = (
            self.db.query(KnowledgeNode)
            .join(lesson_knowledge, KnowledgeNode.id == lesson_knowledge.c.knowledge_node_id)
            .filter(lesson_knowledge.c.lesson_id.in_(lesson_ids))
            .all()
        )

        if not nodes:
            return []

        # Collect all active questions per node with weighting
        weighted_questions = []
        for node in nodes:
            node_questions = [
                q for q in node.questions
                if (not difficulty or q.difficulty == difficulty)
            ]
            for q in node_questions:
                # Repeat entry proportional to importance_weight for weighted sampling
                weighted_questions.extend([(q, node)] * node.importance_weight)

        if not weighted_questions:
            return []

        # Sample without replacement (de-dup by question id after sampling)
        seen_ids = set()
        result = []
        shuffled = random.sample(weighted_questions, min(len(weighted_questions), num_questions * 3))

        for q, node in shuffled:
            if q.id not in seen_ids:
                seen_ids.add(q.id)
                result.append(QuestionItem(
                    question_id=q.id,
                    knowledge_node_id=node.id,
                    knowledge_node_title=node.title,
                    question_type=q.question_type,
                    difficulty=q.difficulty,
                    content=q.content,
                    options=q.options,
                ))
            if len(result) >= num_questions:
                break

        return result

    # ============================================
    # PRACTICE RESULT
    # ============================================

    def submit_result(self, user_id: int, data: PracticeResultCreate) -> PracticeResult:
        """Submit practice results for a session"""
        session = self.get_session_by_id(data.session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your session")

        # Recalculate score server-side for integrity
        if data.total_questions > 0:
            computed_score = round((data.correct_answers / data.total_questions) * 100, 2)
        else:
            computed_score = 0.0

        answers_data = (
            [a.model_dump() for a in data.answers]
            if data.answers else None
        )

        result = PracticeResult(
            session_id=data.session_id,
            total_questions=data.total_questions,
            correct_answers=data.correct_answers,
            score=computed_score,
            time_spent=data.time_spent,
            answers=answers_data,
        )
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def get_results_for_session(self, session_id: int) -> List[PracticeResult]:
        return (
            self.db.query(PracticeResult)
            .filter(PracticeResult.session_id == session_id)
            .order_by(PracticeResult.created_at.desc())
            .all()
        )

    def get_result_by_id(self, result_id: int) -> Optional[PracticeResult]:
        return self.db.query(PracticeResult).filter(PracticeResult.id == result_id).first()

    # ============================================
    # MASTERY ANALYSIS + RECOMMENDATION
    # ============================================

    def analyze_mastery(self, session_id: int, user_id: int) -> MasteryReport:
        """
        Analyze user performance and generate recommendations.

        Mastery thresholds:
          < 40%  → beginner
          40-59% → developing
          60-79% → proficient
          ≥ 80%  → mastered
        """
        session = self.get_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your session")

        results = self.get_results_for_session(session_id)
        if not results:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No practice results for this session")

        # Aggregate across all results in the session
        total_q = sum(r.total_questions for r in results)
        total_correct = sum(r.correct_answers for r in results)
        avg_score = (total_correct / total_q * 100) if total_q > 0 else 0.0

        # Determine mastery level
        if avg_score < 40:
            mastery_level = "beginner"
        elif avg_score < 60:
            mastery_level = "developing"
        elif avg_score < 80:
            mastery_level = "proficient"
        else:
            mastery_level = "mastered"

        # Analyse per-node performance from detailed answers
        node_correct: Dict[int, int] = {}
        node_total: Dict[int, int] = {}

        for result in results:
            if not result.answers:
                continue
            for answer in result.answers:
                # answers stores: {question_id, selected_answer, is_correct, knowledge_node_id, ...}
                node_id = answer.get("knowledge_node_id")
                if node_id is None:
                    continue
                node_total[node_id] = node_total.get(node_id, 0) + 1
                if answer.get("is_correct"):
                    node_correct[node_id] = node_correct.get(node_id, 0) + 1

        weak_node_ids = []
        strong_node_ids = []
        for node_id, total in node_total.items():
            node_score = (node_correct.get(node_id, 0) / total) * 100
            if node_score < 50:
                weak_node_ids.append(node_id)
            elif node_score >= 80:
                strong_node_ids.append(node_id)

        # Generate human-readable recommendations
        recommendations = self._build_recommendations(
            mastery_level, avg_score, weak_node_ids, strong_node_ids, session
        )

        return MasteryReport(
            session_id=session_id,
            total_questions=total_q,
            correct_answers=total_correct,
            score=round(avg_score, 2),
            mastery_level=mastery_level,
            weak_node_ids=weak_node_ids,
            strong_node_ids=strong_node_ids,
            recommendations=recommendations,
        )

    def _build_recommendations(
            self,
            mastery_level: str,
            score: float,
            weak_node_ids: List[int],
            strong_node_ids: List[int],
            session: StudySession,
    ) -> List[str]:
        recs = []

        if mastery_level == "beginner":
            recs.append("Hãy ôn lại các bài học cơ bản trước khi tiếp tục.")
            recs.append("Tập trung vào các khái niệm nền tảng (concept, definition).")
        elif mastery_level == "developing":
            recs.append("Bạn đang tiến bộ! Hãy luyện tập thêm các dạng bài trung bình.")
            recs.append("Xem lại phần lý thuyết của các chủ đề còn yếu.")
        elif mastery_level == "proficient":
            recs.append("Tốt lắm! Hãy thử thách bản thân với các bài nâng cao.")
        else:
            recs.append("Xuất sắc! Bạn đã thành thạo các kiến thức trong buổi học này.")
            recs.append("Hãy chuyển sang các bài học tiếp theo hoặc nâng cao hơn.")

        if weak_node_ids:
            recs.append(f"Cần ôn luyện thêm {len(weak_node_ids)} chủ đề kiến thức còn yếu.")
        if strong_node_ids:
            recs.append(f"Bạn nắm vững {len(strong_node_ids)} chủ đề - hãy giữ vững phong độ!")

        return recs

    # ============================================
    # USER STATS
    # ============================================

    def get_user_stats(self, user_id: int) -> dict:
        """Aggregate learning stats for a user across all sessions"""
        sessions = self.get_sessions_for_user(user_id, limit=1000)
        session_ids = [s.id for s in sessions]

        results = (
            self.db.query(PracticeResult)
            .filter(PracticeResult.session_id.in_(session_ids))
            .all()
        ) if session_ids else []

        total_sessions = len(sessions)
        completed_sessions = sum(1 for s in sessions if s.completed_at)
        total_questions = sum(r.total_questions for r in results)
        total_correct = sum(r.correct_answers for r in results)
        avg_score = (total_correct / total_questions * 100) if total_questions > 0 else 0.0
        total_time = sum(r.time_spent for r in results)

        return {
            "user_id": user_id,
            "total_sessions": total_sessions,
            "completed_sessions": completed_sessions,
            "total_questions_answered": total_questions,
            "total_correct_answers": total_correct,
            "average_score": round(avg_score, 2),
            "total_time_spent_seconds": total_time,
        }


# ============================================
# DEPENDENCY
# ============================================

def get_session_service(db: DBSession = Depends(get_db)) -> SessionService:
    return SessionService(db)