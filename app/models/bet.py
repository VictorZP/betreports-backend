from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from app.database.database import Base
from datetime import datetime

class Bet(Base):
    __tablename__ = "bets"
    
    id = Column(Integer, primary_key=True, index=True)
    notion_id = Column(String, unique=True, index=True)
    date = Column(DateTime, nullable=True)
    tournament = Column(String, nullable=True)
    match = Column(String, nullable=True)
    bet_type = Column(String, nullable=True)
    coefficient = Column(Float, default=1.85)
    total_value = Column(Float, nullable=True)
    score = Column(String, nullable=True)  # Счет матча (например "103-95")
    result = Column(String, nullable=True)  # Текстовый результат из Notion
    won = Column(Boolean, nullable=True)  # Boolean для расчетов
    stake = Column(Float, default=100)  # Сумма ставки (номинал)
    profit = Column(Float, default=0)  # Профит/убыток
    potential_profit = Column(Float, nullable=True)  # Потенциальный профит из Notion
    is_premium = Column(Boolean, default=False)
    screenshot_url = Column(String, nullable=True)
    time = Column(String, nullable=True)
    match_url = Column(String, nullable=True)  # Ссылка на матч
    season = Column(String, default='2024-2025', nullable=True)  # Сезон
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    def calculate_points(self):
        """Рассчитывает сумму очков из счета игры"""
        if not self.score or '-' not in self.score:
            return 0
            
        # Убираем OT и 2OT из счета
        clean_score = self.score.replace(" (OT)", "").replace(" (2OT)", "")
        
        try:
            # Разбиваем счет на части
            parts = clean_score.split('-')
            if len(parts) != 2:
                return 0
                
            # Преобразуем части в числа и суммируем
            score1 = int(parts[0].strip())
            score2 = int(parts[1].strip())
            
            return score1 + score2
            
        except (ValueError, IndexError):
            return 0

    def calculate_profit(self):
        """Рассчитывает профит на основе результата и ставки"""
        if self.won is None or not self.stake:
            return 0
            
        if self.won:
            # При победе: ставка * (коэффициент - 1)
            return round(self.stake * (self.coefficient - 1), 2)
        else:
            # При проигрыше: теряем ставку
            return -self.stake