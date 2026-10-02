# -*- coding: utf-8 -*-
"""Small JSON-backed local question bank."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional


class QuestionBank:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = RLock()
        self.records: List[Dict[str, str]] = []
        self._load_or_create()

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize(cls, record: Dict[str, Any]) -> Optional[Dict[str, str]]:
        question = cls._text(record.get("question", record.get("title")))
        answer = cls._text(record.get("answer"))
        if not question or not answer:
            return None
        return {
            "question": question,
            "type": cls._text(record.get("type")),
            "options": cls._text(record.get("options")),
            "answer": answer,
        }

    @staticmethod
    def _key(record: Dict[str, str]) -> tuple[str, str, str]:
        return record["question"], record["type"], record["options"]

    def _load_or_create(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])
            return
        try:
            with self.path.open("r", encoding="utf-8") as file:
                values = json.load(file)
            source = values.get("questions", []) if isinstance(values, dict) else values
            if not isinstance(source, list):
                raise ValueError("题库必须是数组或包含 questions 数组的对象")
            self.records = [item for item in (self._normalize(x) for x in source) if item]
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError(f"无法读取本地题库 {self.path}: {exc}") from exc

    def _write(self, records: Iterable[Dict[str, str]]) -> None:
        values = list(records)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix="question_bank.", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(values, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def find(self, question: str, question_type: str = "", options: str = "") -> Optional[str]:
        probe = {
            "question": self._text(question),
            "type": self._text(question_type),
            "options": self._text(options),
        }
        with self._lock:
            for record in self.records:
                if self._key(record)[0:3] == (probe["question"], probe["type"], probe["options"]):
                    return record["answer"]
        return None

    def upsert(self, question: str, question_type: str, options: str, answer: str) -> bool:
        record = self._normalize(
            {"question": question, "type": question_type, "options": options, "answer": answer}
        )
        if not record:
            return False
        with self._lock:
            key = self._key(record)
            for index, existing in enumerate(self.records):
                if self._key(existing) == key:
                    if existing == record:
                        return False
                    self.records[index] = record
                    self._write(self.records)
                    return True
            self.records.append(record)
            self._write(self.records)
            return True

    def import_records(self, values: Any) -> Dict[str, int]:
        source = values.get("questions", values.get("records", [])) if isinstance(values, dict) else values
        if not isinstance(source, list):
            raise ValueError("导入文件必须是题目数组，或包含 questions 数组")
        if len(source) > 10000:
            raise ValueError("单次最多导入 10000 道题目")

        imported = 0
        skipped = 0
        with self._lock:
            by_key = {self._key(record): index for index, record in enumerate(self.records)}
            for item in source:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                record = self._normalize(item)
                if not record:
                    skipped += 1
                    continue
                key = self._key(record)
                if key in by_key:
                    self.records[by_key[key]] = record
                else:
                    by_key[key] = len(self.records)
                    self.records.append(record)
                imported += 1
            self._write(self.records)
        return {"imported": imported, "skipped": skipped, "total": len(self.records)}

    def snapshot(self) -> List[Dict[str, str]]:
        with self._lock:
            return [dict(record) for record in self.records]

    def clear(self) -> None:
        with self._lock:
            self.records = []
            self._write(self.records)
