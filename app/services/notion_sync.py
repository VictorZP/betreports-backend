import os
from datetime import datetime
from typing import Any, Dict, Optional
from notion_client import Client
from sqlalchemy.orm import Session
from app.models.bet import Bet
from dotenv import load_dotenv
from .notion_service import NotionService

load_dotenv()

class NotionSync:
    
    def __init__(self, season='2024-2025'):
        """Инициализация с выбранным сезоном"""
        self.season = season
        
        # Выбираем токен и базу в зависимости от сезона
        if season == '2024-2025':
            token = os.getenv('NOTION_TOKEN_2024') or os.getenv('NOTION_TOKEN')
            database_id = os.getenv('NOTION_DATABASE_2024') or os.getenv('NOTION_DATABASE_ID')
        elif season == '2025-2026':
            token = os.getenv('NOTION_TOKEN_2025')
            database_id = os.getenv('NOTION_DATABASE_2025')
        else:
            token = os.getenv('NOTION_TOKEN_2024') or os.getenv('NOTION_TOKEN')
            database_id = os.getenv('NOTION_DATABASE_2024') or os.getenv('NOTION_DATABASE_ID')
        
        if not token or not database_id:
            print(f"WARNING: Missing credentials for season {season}")
        
        self.notion = Client(auth=token)
        self.database_id = database_id

    def parse_notion_text(self, prop):
        """Парсинг текстовых полей из Notion"""
        if not prop:
            return None
        
        if prop['type'] == 'title':
            if prop['title']:
                return prop['title'][0]['plain_text']
        elif prop['type'] == 'rich_text':
            if prop['rich_text']:
                text_parts = []
                for item in prop['rich_text']:
                    if 'plain_text' in item:
                        text_parts.append(item['plain_text'])
                return ''.join(text_parts) if text_parts else None
        elif prop['type'] == 'select':
            if prop['select']:
                return prop['select']['name']
        
        return None

    def parse_notion_formula(self, prop):
        """Парсинг полей-формул из Notion"""
        if not prop or prop['type'] != 'formula':
            return None
        
        formula = prop.get('formula', {})
        
        if formula.get('type') == 'string':
            return formula.get('string')
        elif formula.get('type') == 'number':
            return formula.get('number')
        elif formula.get('type') == 'boolean':
            return formula.get('boolean')
        
        return None

    def parse_notion_number(self, prop):
        """Парсинг числовых полей из Notion"""
        if not prop:
            return None
        
        if prop['type'] == 'number':
            return prop.get('number')
        elif prop['type'] == 'formula':
            formula = prop.get('formula')
            if formula and formula['type'] == 'number':
                return formula.get('number')
        
        return None

    def parse_notion_date(self, prop):
        """Парсинг даты из Notion"""
        if not prop:
            return None
        
        if prop['type'] == 'date' and prop['date']:
            date_str = prop['date']['start']
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except:
                return None
        
        return None

    def parse_notion_checkbox(self, prop):
        """Парсинг чекбоксов из Notion"""
        if not prop:
            return False
        
        if prop['type'] == 'checkbox':
            return prop.get('checkbox', False)
        
        return False

    def parse_screenshot_url(self, prop):
        """Парсинг URL скриншота из Notion"""
        if not prop:
            return None
        
        if prop['type'] == 'url':
            return prop.get('url')
        elif prop['type'] == 'rich_text' and prop['rich_text']:
            return prop['rich_text'][0].get('plain_text')
        
        return None

    def parse_notion_formula(self, prop):
        """Парсинг полей-формул из Notion"""
        if not prop or prop['type'] != 'formula':
            return None
        
        formula = prop.get('formula', {})
        
        # Если формула возвращает строку
        if formula.get('type') == 'string':
            return formula.get('string')
        # Если формула возвращает число
        elif formula.get('type') == 'number':
            return formula.get('number')
        # Если формула возвращает boolean
        elif formula.get('type') == 'boolean':
            return formula.get('boolean')
        
        return None

    def sync_with_notion(self, db: Session) -> Dict[str, Any]:
        """Синхронизация данных из Notion в базу данных"""
        try:
            if not self.database_id:
                return {
                    "success": False,
                    "message": f"База данных для сезона {self.season} не настроена",
                    "stats": None
                }
            
            print(f"Fetching data from Notion for season {self.season}...")
            
            response = self.notion.databases.query(
                database_id=self.database_id,
                page_size=100
            )
            
            results = response["results"]
            
            while response.get("has_more"):
                response = self.notion.databases.query(
                    database_id=self.database_id,
                    start_cursor=response["next_cursor"],
                    page_size=100
                )
                results.extend(response["results"])
            
            print(f"Found {len(results)} records in Notion")
            
            stats = {
                "total": len(results),
                "created": 0,
                "updated": 0,
                "errors": 0,
                "wins": 0,
                "losses": 0,
                "no_result": 0
            }
            
            for row in results:
                try:
                    properties = row["properties"]
                    
                    notion_id = row["id"]
                    date = self.parse_notion_date(properties.get("Date"))
                    tournament = self.parse_notion_text(properties.get("Турнир"))
                    
                    team1 = self.parse_notion_text(properties.get("Команда 1"))
                    team2 = self.parse_notion_text(properties.get("Команда 2"))
                    match = f"{team1} vs {team2}" if team1 and team2 else None
                    
                    bet_type = self.parse_notion_text(properties.get("Ставка"))
                    total_value = self.parse_notion_number(properties.get("Значение тотала"))
                    score = self.parse_notion_text(properties.get("Итог"))
                    
                    # Парсим результат (формула с эмодзи)
                    result_prop = properties.get("Результат")
                    result_text = None
                    won = None
                    
                    if result_prop and result_prop['type'] == 'formula':
                        result_text = self.parse_notion_formula(result_prop)
                    elif result_prop:
                        result_text = self.parse_notion_text(result_prop)
                    
                    if result_text:
                        if '✅' in result_text:
                            won = True
                            result_text = "WIN"
                            stats["wins"] += 1
                        elif '❌' in result_text:
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
                    
                    # Коэффициент
                    coefficient = 1.85
                    
                    # Парсим профит (тоже формула)
                    profit_prop = properties.get("Потенциальный профит")
                    profit = None
                    
                    if profit_prop and profit_prop['type'] == 'formula':
                        profit = self.parse_notion_formula(profit_prop)
                    elif profit_prop:
                        profit = self.parse_notion_number(profit_prop)
                    
                    # Базовая ставка
                    stake = 100.0
                    
                    # Если профита нет, вычисляем
                    if profit is None and won is not None:
                        if won:
                            profit = stake * 0.85
                        else:
                            profit = -stake
                    
                    # Парсим остальные поля
                    is_premium = self.parse_notion_checkbox(properties.get("Премиум"))
                    time_str = self.parse_notion_text(properties.get("Время ставки"))
                    
                    screenshot_url = None
                    if "Скрин из бота" in properties:
                        screenshot_url = self.parse_screenshot_url(properties["Скрин из бота"])
                    
                    match_url = None
                    if 'Ссылка на матч' in properties:
                        url_prop = properties['Ссылка на матч']
                        if url_prop.get('type') == 'url' and url_prop.get('url'):
                            match_url = url_prop['url']
                    
                    # Сохраняем в БД
                    existing_bet = db.query(Bet).filter(Bet.notion_id == notion_id).first()
                    
                    if existing_bet:
                        print(f"Updating existing bet {notion_id}")
                        existing_bet.date = date
                        existing_bet.tournament = tournament
                        existing_bet.match = match
                        existing_bet.bet_type = bet_type
                        existing_bet.coefficient = coefficient
                        existing_bet.total_value = total_value
                        existing_bet.score = score
                        existing_bet.result = result_text
                        existing_bet.won = won
                        existing_bet.stake = stake
                        existing_bet.profit = profit or 0
                        existing_bet.is_premium = is_premium
                        existing_bet.screenshot_url = screenshot_url
                        existing_bet.match_url = match_url
                        existing_bet.time = time_str
                        existing_bet.season = self.season
                        existing_bet.updated_at = datetime.utcnow()
                        stats["updated"] += 1
                    else:
                        print(f"Creating new bet {notion_id}")
                        new_bet = Bet(
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
                            updated_at=datetime.utcnow()
                        )
                        db.add(new_bet)
                        stats["created"] += 1
                    
                except Exception as e:
                    print(f"Error processing row {row.get('id')}: {e}")
                    stats["errors"] += 1
                    continue
            
            db.commit()
            
            print(f"\nSync completed:")
            print(f"  Created: {stats['created']}")
            print(f"  Updated: {stats['updated']}")
            print(f"  Wins: {stats['wins']}")
            print(f"  Losses: {stats['losses']}")
            print(f"  No result: {stats['no_result']}")
            
            return {
                "success": True,
                "message": f"Синхронизация завершена успешно",
                "stats": stats
            }
            
        except Exception as e:
            print(f"Sync error: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return {
                "success": False,
                "message": f"Ошибка синхронизации: {str(e)}",
                "stats": None
            }