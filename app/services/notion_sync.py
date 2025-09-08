# app/services/notion_sync.py
import os
from datetime import datetime
from typing import Any, Dict, Optional
from notion_client import Client
from sqlalchemy.orm import Session
from app.models.bet import Bet
from dotenv import load_dotenv

load_dotenv()

class NotionSync:
    def __init__(self, season: Optional[str] = None):
        """Инициализация с выбранным сезоном и стабильным маппингом env-переменных."""
        # Нормализуем сезон (по умолчанию берем из DEFAULT_SEASON, иначе '2024')
        season = (season or os.getenv("DEFAULT_SEASON") or "2024").strip()
        self.season = season

        # Явный маппинг сезонов → пар переменных
        # Добавь сюда новые сезоны по мере необходимости
        mapping = {
            "2024":       ("NOTION_TOKEN_2024", "NOTION_DATABASE_2024"),
            "2024-2025":  ("NOTION_TOKEN_2024", "NOTION_DATABASE_2024"),
            "2025":       ("NOTION_TOKEN_2025", "NOTION_DATABASE_2025"),
            "2025-2026":  ("NOTION_TOKEN_2025", "NOTION_DATABASE_2025"),
        }

        token_key, db_key = mapping.get(season, ("NOTION_TOKEN_2024", "NOTION_DATABASE_2024"))

        token = os.getenv(token_key) or os.getenv("NOTION_TOKEN")
        database_id = os.getenv(db_key) or os.getenv("NOTION_DATABASE_ID")

        if not token or not database_id:
            print(f"WARNING: Missing Notion credentials for season '{season}' "
                  f"(checked {token_key}/{db_key} and NOTION_TOKEN/NOTION_DATABASE_ID)")

        self.notion = Client(auth=token)
        self.database_id = database_id

    # ==== Хелперы парсинга свойств Notion ====

    def _parse_text(self, prop):
        if not prop:
            return None
        t = prop.get("type")
        if t == "title" and prop.get("title"):
            return prop["title"][0].get("plain_text")
        if t == "rich_text" and prop.get("rich_text"):
            return "".join(x.get("plain_text", "") for x in prop["rich_text"])
        if t == "select" and prop.get("select"):
            return prop["select"].get("name")
        return None

    def _parse_number(self, prop):
        if not prop:
            return None
        t = prop.get("type")
        if t == "number":
            return prop.get("number")
        if t == "formula":
            f = prop.get("formula") or {}
            if f.get("type") == "number":
                return f.get("number")
        return None

    def _parse_formula(self, prop):
        if not prop or prop.get("type") != "formula":
            return None
        f = prop.get("formula") or {}
        if f.get("type") == "string":
            return f.get("string")
        if f.get("type") == "number":
            return f.get("number")
        if f.get("type") == "boolean":
            return f.get("boolean")
        return None

    def _parse_date(self, prop):
        if not prop:
            return None
        if prop.get("type") == "date" and prop.get("date"):
            s = prop["date"].get("start")
            if not s:
                return None
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                return None
        return None

    def _parse_checkbox(self, prop) -> bool:
        if not prop:
            return False
        if prop.get("type") == "checkbox":
            return prop.get("checkbox", False)
        return False

    def _parse_url_or_text_url(self, prop):
        if not prop:
            return None
        t = prop.get("type")
        if t == "url":
            return prop.get("url")
        if t == "rich_text" and prop.get("rich_text"):
            return prop["rich_text"][0].get("plain_text")
        return None

    # ==== Основной синк ====

    def sync_with_notion(self, db: Session) -> Dict[str, Any]:
        """Синхронизация данных из Notion в базу данных."""
        try:
            if not self.database_id:
                return {
                    "success": False,
                    "message": f"База данных для сезона {self.season} не настроена",
                    "stats": None
                }

            print(f"[sync] Fetching data from Notion for season '{self.season}'...")
            response = self.notion.databases.query(database_id=self.database_id, page_size=100)
            results = list(response.get("results", []))

            while response.get("has_more"):
                response = self.notion.databases.query(
                    database_id=self.database_id,
                    start_cursor=response.get("next_cursor"),
                    page_size=100
                )
                results.extend(response.get("results", []))

            print(f"[sync] Found {len(results)} records in Notion")

            stats = {"total": len(results), "created": 0, "updated": 0, "errors": 0,
                     "wins": 0, "losses": 0, "no_result": 0}

            for row in results:
                try:
                    p = row.get("properties", {})
                    notion_id = row.get("id")

                    date = self._parse_date(p.get("Date"))
                    tournament = self._parse_text(p.get("Турнир"))

                    team1 = self._parse_text(p.get("Команда 1"))
                    team2 = self._parse_text(p.get("Команда 2"))
                    match = f"{team1} vs {team2}" if team1 and team2 else None

                    bet_type = self._parse_text(p.get("Ставка"))
                    total_value = self._parse_number(p.get("Значение тотала"))
                    score = self._parse_text(p.get("Итог"))

                    # Результат (формула/текст с эмодзи)
                    result_prop = p.get("Результат")
                    result_text = None
                    won = None

                    if result_prop and result_prop.get("type") == "formula":
                        result_text = self._parse_formula(result_prop)
                    elif result_prop:
                        result_text = self._parse_text(result_prop)

                    if result_text:
                        if "✅" in result_text:
                            won = True
                            result_text = "WIN"
                            stats["wins"] += 1
                        elif "❌" in result_text:
                            won = False
                            result_text = "LOSE"
                            stats["losses"] += 1
                        else:
                            won = None
                            result_text = "-"
                            stats["no_result"] += 1
                    else:
                        won = None
                        result_text = "-"
                        stats["no_result"] += 1

                    # Коэф/ставка/профит (дефолты)
                    coefficient = 1.85
                    stake = 100.0
                    profit_prop = p.get("Потенциальный профит")
                    profit = None
                    if profit_prop and profit_prop.get("type") == "formula":
                        profit = self._parse_formula(profit_prop)
                    elif profit_prop:
                        profit = self._parse_number(profit_prop)
                    if profit is None and won is not None:
                        profit = stake * 0.85 if won else -stake

                    is_premium = self._parse_checkbox(p.get("Премиум"))
                    time_str = self._parse_text(p.get("Время ставки"))
                    screenshot_url = self._parse_url_or_text_url(p.get("Скрин из бота"))

                    match_url = None
                    if "Ссылка на матч" in p:
                        prop_url = p["Ссылка на матч"]
                        if prop_url.get("type") == "url" and prop_url.get("url"):
                            match_url = prop_url["url"]

                    existing = db.query(Bet).filter(Bet.notion_id == notion_id).first()
                    if existing:
                        # update
                        existing.date = date
                        existing.tournament = tournament
                        existing.match = match
                        existing.bet_type = bet_type
                        existing.coefficient = coefficient
                        existing.total_value = total_value
                        existing.score = score
                        existing.result = result_text
                        existing.won = won
                        existing.stake = stake
                        existing.profit = profit or 0
                        existing.is_premium = is_premium
                        existing.screenshot_url = screenshot_url
                        existing.match_url = match_url
                        existing.time = time_str
                        existing.season = self.season
                        existing.updated_at = datetime.utcnow()
                        stats["updated"] += 1
                    else:
                        # create
                        db.add(Bet(
                            notion_id=notion_id,
                            date=date,
                            tournament=tournament,
                            match=match,
                            bet_type=bet_type,
                            coefficient=coefficient,
                            total_value=total_value,
                            score=score,
                            result=result_text,
                            won=won,
                            stake=stake,
                            profit=profit or 0,
                            is_premium=is_premium,
                            screenshot_url=screenshot_url,
                            match_url=match_url,
                            time=time_str,
                            season=self.season,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        ))
                        stats["created"] += 1

                except Exception as e:
                    print(f"[sync] Error processing row {row.get('id')}: {e}")
                    stats["errors"] += 1
                    continue

            db.commit()
            print(f"[sync] Done. Created={stats['created']} Updated={stats['updated']} "
                  f"Wins={stats['wins']} Losses={stats['losses']} NoRes={stats['no_result']}")

            return {"success": True, "message": "Синхронизация завершена успешно", "stats": stats}

        except Exception as e:
            print(f"[sync] Fatal error: {e}")
            import traceback; traceback.print_exc()
            db.rollback()
            return {"success": False, "message": f"Ошибка синхронизации: {e}", "stats": None}
