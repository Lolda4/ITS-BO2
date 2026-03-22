"""
ResultStore – Ukládání a načítání JSON výsledků testů.

Výsledky se ukládají jako JSON soubory do results/{session_id}.json.
Žádná databáze – jednoduchost a exportovatelnost.

Každý výsledek obsahuje kompletní kontext: UC profil, effective_params,
measured metriky, evaluaci s normativními prahy, interpretation text,
OBU-reported stats, a baseline referenci.
"""

import json
import logging
import os
from typing import Optional

from config import RESULTS_DIR

logger = logging.getLogger("itsbo.core.result_store")


class ResultStore:
    """
    Ukládání a načítání výsledků testů jako JSON soubory.

    Soubory se ukládají do RESULTS_DIR/{session_id}.json.
    Adresář se vytvoří automaticky pokud neexistuje.
    """

    def __init__(self) -> None:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        logger.info("ResultStore initialized at '%s'", RESULTS_DIR)

    def save(self, session_id: str, result: dict) -> str:
        """
        Uloží výsledek testu.

        Args:
            session_id: identifikátor session (= test_id).
            result: kompletní výsledkový dict.

        Returns:
            str: absolutní cesta k uloženému souboru.
        """
        filepath = os.path.join(RESULTS_DIR, f"{session_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)

        logger.info("Result saved: %s (%d bytes)", filepath, os.path.getsize(filepath))
        return os.path.abspath(filepath)

    def get_result(self, session_id: str) -> Optional[dict]:
        """
        Načte výsledek testu.

        Args:
            session_id: identifikátor session.

        Returns:
            dict: výsledek nebo None pokud neexistuje.
        """
        filepath = os.path.join(RESULTS_DIR, f"{session_id}.json")
        if not os.path.exists(filepath):
            logger.warning("Result not found: %s", filepath)
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_results(self, limit: int = 100) -> list[dict]:
        """
        Seznam všech výsledků seřazený od nejnovějšího.

        Každý záznam obsahuje metadata (test_id, uc_profile, session_status,
        overall_pass, started_at, duration_s) bez plných measured dat.

        Args:
            limit: max počet výsledků.

        Returns:
            list[dict]: seznam výsledků s metadaty.
        """
        entries: list[dict] = []

        if not os.path.exists(RESULTS_DIR):
            return entries

        for filename in os.listdir(RESULTS_DIR):
            if not filename.endswith(".json"):
                continue

            filepath = os.path.join(RESULTS_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    result = json.load(f)

                entries.append({
                    "test_id": result.get("test_id", filename[:-5]),
                    "uc_profile": result.get("uc_profile"),
                    "uc_name": result.get("uc_name"),
                    "session_status": result.get("session_status"),
                    "overall_pass": result.get("overall_pass"),
                    "started_at": result.get("started_at"),
                    "duration_s": result.get("duration_s"),
                    "network_condition": result.get("network_condition"),
                    "label": result.get("label"),
                    "interpretation": result.get("interpretation"),
                    "file_size_bytes": os.path.getsize(filepath),
                })
            except Exception as e:
                logger.warning("Failed to read result %s: %s", filename, e)

        # Seřadit desc dle started_at (newest first)
        entries.sort(key=lambda x: x.get("started_at") or "", reverse=True)
        return entries[:limit]

    def delete_result(self, session_id: str) -> bool:
        """Smaže výsledek (pro debugging)."""
        filepath = os.path.join(RESULTS_DIR, f"{session_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info("Result deleted: %s", filepath)
            return True
        return False
