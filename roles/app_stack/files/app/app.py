from __future__ import annotations

import os
from contextlib import closing
from typing import Any

import pymysql
from flask import Flask, jsonify

app = Flask(__name__)

APP_COLOR = os.getenv("APP_COLOR", "unknown")
APP_VERSION = os.getenv("APP_VERSION", "0.0.0")
APP_MESSAGE = os.getenv("APP_MESSAGE", "Ansible + Docker advanced lab")


def db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("DB_HOST", "db"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "labuser"),
        "password": os.environ["DB_PASSWORD"],
        "database": os.getenv("DB_NAME", "labdb"),
        "connect_timeout": 3,
        "read_timeout": 5,
        "write_timeout": 5,
        "autocommit": True,
        "cursorclass": pymysql.cursors.DictCursor,
    }


def get_connection() -> pymysql.connections.Connection:
    return pymysql.connect(**db_config())


def ensure_schema_and_record_visit() -> int:
    with closing(get_connection()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS visits (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    release_color VARCHAR(16) NOT NULL,
                    release_version VARCHAR(32) NOT NULL,
                    visited_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id)
                ) ENGINE=InnoDB
                """
            )
            cursor.execute(
                "INSERT INTO visits (release_color, release_version) VALUES (%s, %s)",
                (APP_COLOR, APP_VERSION),
            )
            cursor.execute("SELECT COUNT(*) AS total FROM visits")
            row = cursor.fetchone()
            return int(row["total"])


@app.get("/health")
def health():
    try:
        with closing(get_connection()) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                row = cursor.fetchone()
        return jsonify(status="ok", database="connected", db_check=row["ok"]), 200
    except Exception as exc:  # 실습에서는 장애 내용을 바로 관찰하도록 단순화
        return jsonify(status="error", database="disconnected", error=str(exc)), 503


@app.get("/api/info")
def info():
    try:
        total_visits = ensure_schema_and_record_visit()
        return jsonify(
            status="ok",
            color=APP_COLOR,
            version=APP_VERSION,
            message=APP_MESSAGE,
            database="connected",
            total_visits=total_visits,
        )
    except Exception as exc:
        return jsonify(status="error", database="disconnected", error=str(exc)), 503


@app.get("/")
def index():
    return f"""
    <!doctype html>
    <html lang="ko">
      <head><meta charset="utf-8"><title>Ansible Docker Lab</title></head>
      <body>
        <h1>Ansible + Docker 고급 실습</h1>
        <p>활성 릴리스: <strong>{APP_COLOR}</strong></p>
        <p>버전: <strong>{APP_VERSION}</strong></p>
        <p>{APP_MESSAGE}</p>
        <p><a href="/api/info">통합 API 확인</a></p>
      </body>
    </html>
    """, 200
