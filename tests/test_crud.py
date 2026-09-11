"""数据库 CRUD 操作测试 - 用内存 SQLite 测试各表读写。

测试覆盖：
1. create_document + get_document_by_id
2. update_document_status
3. get_documents 按租户/状态过滤
4. bulk_create_chunks + get_chunks_by_doc
5. create_query_log + add_query_sources + get_query_logs
6. create_feedback + get_feedbacks + get_negative_feedbacks
7. create_evaluation
8. create_ingestion_task + update_ingestion_task
9. create_user + get_user_by_username + verify_password
10. get_stats 统计汇总
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import crud
from app.db.database import Base


@pytest.fixture
def db_session():
    """内存 SQLite 数据库，每个测试独立。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()


class TestDocumentCRUD:
    """文档表 CRUD 测试。"""

    def test_create_and_get(self, db_session):
        doc = crud.create_document(
            db_session, doc_name="测试文档", file_path="/tmp/test.pdf",
            file_type="pdf", classification="internal", tenant_id="tenant_a",
        )
        assert doc.id > 0
        assert doc.doc_name == "测试文档"
        assert doc.status == "pending"

        got = crud.get_document_by_id(db_session, doc.id)
        assert got is not None
        assert got.doc_name == "测试文档"

    def test_update_status(self, db_session):
        doc = crud.create_document(
            db_session, doc_name="doc2", file_path="/tmp/x.txt",
            file_type="txt",
        )
        updated = crud.update_document_status(
            db_session, doc.id, status="ready", chunk_count=5,
        )
        assert updated.status == "ready"
        assert updated.chunk_count == 5

    def test_get_by_tenant(self, db_session):
        crud.create_document(
            db_session, doc_name="a", file_path="/a", file_type="txt",
            tenant_id="t1",
        )
        crud.create_document(
            db_session, doc_name="b", file_path="/b", file_type="txt",
            tenant_id="t2",
        )
        results = crud.get_documents(db_session, tenant_id="t1")
        assert len(results) == 1
        assert results[0].doc_name == "a"

    def test_get_by_status(self, db_session):
        crud.create_document(
            db_session, doc_name="ready_doc", file_path="/r", file_type="txt",
        )
        crud.create_document(
            db_session, doc_name="pending_doc", file_path="/p", file_type="txt",
        )
        crud.update_document_status(db_session, 1, status="ready")
        results = crud.get_documents(db_session, status="ready")
        assert len(results) == 1
        assert results[0].doc_name == "ready_doc"


class TestChunkCRUD:
    """切片元信息表测试。"""

    def test_bulk_create_and_get(self, db_session):
        doc = crud.create_document(
            db_session, doc_name="d", file_path="/d", file_type="txt",
        )
        chunks_data = [
            {"chunk_id": "c1", "chunk_index": 0, "heading_number": "1",
             "heading_title": "title1", "heading_level": 1,
             "content_preview": "preview1", "token_count": 10, "classification": "public"},
            {"chunk_id": "c2", "chunk_index": 1, "heading_number": "2",
             "heading_title": "title2", "heading_level": 1,
             "content_preview": "preview2", "token_count": 15, "classification": "internal"},
        ]
        count = crud.bulk_create_chunks(db_session, doc.id, chunks_data)
        assert count == 2

        chunks = crud.get_chunks_by_doc(db_session, doc.id)
        assert len(chunks) == 2
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1

    def test_empty_chunks(self, db_session):
        count = crud.bulk_create_chunks(db_session, 999, [])
        assert count == 0


class TestQueryLogCRUD:
    """查询日志表测试。"""

    def test_create_log_and_sources(self, db_session):
        log = crud.create_query_log(
            db_session, trace_id="trace_001", tenant_id="t1",
            user_clearance="public", question="什么是算力", top_k=5,
            sources_count=3, answer_preview="算力是计算能力",
            elapsed_ms=120, cache_hit=False, degraded=False,
            llm_used=True,
        )
        assert log.id > 0
        assert log.question == "什么是算力"

        sources_data = [
            {"rank": 1, "chunk_id": "c1", "doc_name": "doc1",
             "heading_number": "1", "dense_score": 0.9,
             "sparse_score": 0.5, "rrf_score": 0.02},
            {"rank": 2, "chunk_id": "c2", "doc_name": "doc2",
             "heading_number": "2", "dense_score": 0.7,
             "sparse_score": 0.3, "rrf_score": 0.015},
        ]
        count = crud.add_query_sources(db_session, log.id, sources_data)
        assert count == 2

    def test_get_logs_by_tenant(self, db_session):
        crud.create_query_log(
            db_session, trace_id="t1", tenant_id="tenant_a",
            user_clearance="public", question="q1", top_k=5,
        )
        crud.create_query_log(
            db_session, trace_id="t2", tenant_id="tenant_b",
            user_clearance="public", question="q2", top_k=5,
        )
        logs = crud.get_query_logs(db_session, tenant_id="tenant_a")
        assert len(logs) == 1
        assert logs[0].question == "q1"

    def test_get_log_by_trace(self, db_session):
        crud.create_query_log(
            db_session, trace_id="trace_xyz", tenant_id="t",
            user_clearance="public", question="q", top_k=5,
        )
        log = crud.get_query_log_by_trace(db_session, "trace_xyz")
        assert log is not None
        assert log.question == "q"

        assert crud.get_query_log_by_trace(db_session, "nonexistent") is None


class TestFeedbackCRUD:
    """用户反馈表测试。"""

    def test_create_and_get(self, db_session):
        log = crud.create_query_log(
            db_session, trace_id="t", tenant_id="t",
            user_clearance="public", question="q", top_k=5,
        )
        fb = crud.create_feedback(
            db_session, query_log_id=log.id, feedback_type="up",
        )
        assert fb.id > 0

        fbs = crud.get_feedbacks(db_session, feedback_type="up")
        assert len(fbs) == 1

    def test_negative_feedbacks(self, db_session):
        log = crud.create_query_log(
            db_session, trace_id="t", tenant_id="t",
            user_clearance="public", question="q", top_k=5,
        )
        crud.create_feedback(
            db_session, query_log_id=log.id, feedback_type="down",
            corrected_answer="正确答案", comment="回答不准确",
        )
        neg = crud.get_negative_feedbacks(db_session)
        assert len(neg) == 1
        assert neg[0].feedback_type == "down"
        assert neg[0].corrected_answer == "正确答案"


class TestEvaluationCRUD:
    """评测结果表测试。"""

    def test_create_evaluation(self, db_session):
        log = crud.create_query_log(
            db_session, trace_id="t", tenant_id="t",
            user_clearance="public", question="q", top_k=5,
        )
        ev = crud.create_evaluation(
            db_session, query_log_id=log.id,
            recall_at_k=0.85, faithfulness=0.9, hallucination_rate=0.05,
        )
        assert ev.id > 0
        assert ev.recall_at_k == 0.85
        assert ev.faithfulness == 0.9


class TestIngestionTaskCRUD:
    """入库任务表测试。"""

    def test_create_and_update(self, db_session):
        task = crud.create_ingestion_task(
            db_session, celery_task_id="celery_001",
            file_path="/tmp/test.pdf", doc_name="测试", classification="internal",
        )
        assert task.id > 0
        assert task.status == "pending"

        updated = crud.update_ingestion_task(
            db_session, celery_task_id="celery_001", status="started",
        )
        assert updated.status == "started"
        assert updated.started_at is not None

        updated = crud.update_ingestion_task(
            db_session, celery_task_id="celery_001", status="success",
            document_id=1,
        )
        assert updated.status == "success"
        assert updated.completed_at is not None

    def test_update_nonexistent(self, db_session):
        result = crud.update_ingestion_task(
            db_session, celery_task_id="nonexistent", status="success",
        )
        assert result is None


class TestUserCRUD:
    """用户表测试。"""

    def test_create_and_get(self, db_session):
        user = crud.create_user(
            db_session, username="testuser", password="pass123",
            clearance="internal", display_name="测试用户",
            tenant_id="tenant_a", dept="dev",
        )
        assert user.id > 0
        assert user.username == "testuser"
        assert user.clearance == "internal"
        assert user.password_hash != "pass123"

        got = crud.get_user_by_username(db_session, "testuser")
        assert got is not None
        assert got.display_name == "测试用户"

    def test_get_nonexistent_user(self, db_session):
        assert crud.get_user_by_username(db_session, "ghost") is None

    def test_count_users(self, db_session):
        assert crud.count_users(db_session) == 0
        crud.create_user(db_session, username="u1", password="p1")
        crud.create_user(db_session, username="u2", password="p2")
        assert crud.count_users(db_session) == 2


class TestStats:
    """统计汇总测试。"""

    def test_empty_stats(self, db_session):
        stats = crud.get_stats(db_session)
        assert stats["documents"] == 0
        assert stats["queries"] == 0
        assert stats["feedbacks"] == 0

    def test_stats_after_inserts(self, db_session):
        doc = crud.create_document(
            db_session, doc_name="d", file_path="/d", file_type="txt",
        )
        crud.bulk_create_chunks(db_session, doc.id, [
            {"chunk_id": "c1", "chunk_index": 0, "heading_number": "1",
             "heading_title": "t", "heading_level": 1,
             "content_preview": "p", "token_count": 5, "classification": "public"},
        ])
        log = crud.create_query_log(
            db_session, trace_id="t", tenant_id="t",
            user_clearance="public", question="q", top_k=5,
        )
        crud.create_feedback(db_session, query_log_id=log.id, feedback_type="up")

        stats = crud.get_stats(db_session)
        assert stats["documents"] == 1
        assert stats["chunks"] == 1
        assert stats["queries"] == 1
        assert stats["feedbacks"] == 1
        assert stats["up_votes"] == 1
        assert stats["down_votes"] == 0
