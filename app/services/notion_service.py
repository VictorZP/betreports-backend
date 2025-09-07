import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from notion_client import Client
import pytz

class NotionService:
    def __init__(self):
        self.notion = Client(auth=os.getenv("NOTION_TOKEN"))
        self.database_id = os.getenv("NOTION_DATABASE_ID")
        self.paris_tz = pytz.timezone('Europe/Paris')
        self.utc_tz = pytz.UTC
        
    def parse_notion_property(self, prop: Dict[str, Any], prop_type: str) -> Any:
        """Универсальный парсер свойств Notion"""
        if not prop:
            return None
            
        try:
            if prop_type == "title":
                return prop["title"][0]["plain_text"] if prop.get("title") else None
            elif prop_type == "rich_text":
                return prop["rich_text"][0]["plain_text"] if prop.get("rich_text") else None
            elif prop_type == "number":
                return prop.get("number")
            elif prop_type == "select":
                return prop["select"]["name"] if prop.get("select") else None
            elif prop_type == "date":
                if prop.get("date") and prop["date"].get("start"):
                    date_str = prop["date"]["start"]
                    # Парсим дату и конвертируем из парижского времени
                    if "T" in date_str:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = self.paris_tz.localize(dt)
                        return dt.astimezone(self.utc_tz).replace(tzinfo=None)
                    return datetime.strptime(date_str, "%Y-%m-%d")
                return None
            elif prop_type == "checkbox":
                return prop.get("checkbox", False)
            elif prop_type == "url" or prop_type == "screenshot":
                # Обработка скриншотов - проверяем разные типы полей
                if prop.get("url"):
                    return prop["url"]
                elif prop.get("rich_text") and prop["rich_text"]:
                    text = prop["rich_text"][0]
                    # Проверяем href в rich_text
                    if text.get("href"):
                        return text["href"]
                    # Или просто текст со ссылкой
                    plain_text = text.get("plain_text", "")
                    if "http" in plain_text:
                        return plain_text
                elif prop.get("files") and prop["files"]:
                    # Если это файл
                    file = prop["files"][0]
                    if file.get("type") == "external":
                        return file.get("external", {}).get("url")
                    elif file.get("type") == "file":
                        return file.get("file", {}).get("url")
                return None
            else:
                return None
        except Exception as e:
            print(f"Error parsing {prop_type}: {e}")
            return None
    
    def sync_bets(self) -> List[Dict[str, Any]]:
        """Полная синхронизация всех ставок"""
        return self._fetch_bets()
    
    def sync_recent_bets(self, since_date: datetime) -> List[Dict[str, Any]]:
        """Синхронизация только недавних ставок"""
        return self._fetch_bets(filter_date=since_date)
    
    def _fetch_bets(self, filter_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Получение ставок из Notion с опциональной фильтрацией по дате"""
        all_bets = []
        
        try:
            # Формируем фильтр если нужно
            filter_params = {}
            if filter_date:
                filter_params = {
                    "filter": {
                        "property": "Дата",
                        "date": {
                            "after": filter_date.isoformat()
                        }
                    }
                }
            
            # Первый запрос
            response = self.notion.databases.query(
                database_id=self.database_id,
                page_size=100,
                **filter_params
            )
            
            results = response["results"]
            
            # Получаем остальные страницы
            while response.get("has_more"):
                response = self.notion.databases.query(
                    database_id=self.database_id,
                    start_cursor=response["next_cursor"],
                    page_size=100,
                    **filter_params
                )
                results.extend(response["results"])
            
            print(f"Получено {len(results)} записей из Notion")
            
            # Парсим каждую запись
            for row in results:
                try:
                    props = row["properties"]
                    
                    bet_data = {
                        "notion_id": row["id"],
                        "date": self.parse_notion_property(props.get("Дата"), "date"),
                        "tournament": self.parse_notion_property(props.get("Турнир"), "select"),
                        "team1": self.parse_notion_property(props.get("Команда 1"), "title"),
                        "team2": self.parse_notion_property(props.get("Команда 2"), "rich_text"),
                        "bet_type": self.parse_notion_property(props.get("Тип ставки"), "select"),
                        "total_value": self.parse_notion_property(props.get("Тотал"), "number"),
                        "game_score": self.parse_notion_property(props.get("Счет игры"), "rich_text"),
                        "result": self.parse_notion_property(props.get("Результат"), "select"),
                        "points": self.parse_notion_property(props.get("Очки"), "number"),
                        "profit": self.parse_notion_property(props.get("Профит"), "number"),
                        "nominal": self.parse_notion_property(props.get("Номинал"), "number"),
                        "bank": self.parse_notion_property(props.get("Банк"), "number"),
                        "is_premium": self.parse_notion_property(props.get("Премиум"), "checkbox"),
                        "screenshot": self.parse_notion_property(props.get("Скрин из бота"), "screenshot"),
                    }
                    
                    # Добавляем только если есть хотя бы команды
                    if bet_data["team1"] or bet_data["team2"]:
                        all_bets.append(bet_data)
                    
                except Exception as e:
                    print(f"Ошибка парсинга записи {row.get('id')}: {e}")
                    continue
            
            return all_bets
            
        except Exception as e:
            print(f"Ошибка при получении данных из Notion: {e}")
            import traceback
            traceback.print_exc()
            return []
        
