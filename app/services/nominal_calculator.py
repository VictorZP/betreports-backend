from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from ..models.bet import Bet

class NominalCalculator:
    @staticmethod
    def get_first_monday_of_month(date):
        """Получает дату первого понедельника месяца"""
        first_day = date.replace(day=1)
        while first_day.weekday() != 0:  # 0 = Понедельник
            first_day += timedelta(days=1)
        return first_day

    @staticmethod
    def calculate_monthly_nominal(db: Session, date: datetime):
        """Рассчитывает номинал на месяц"""
        # Начальные значения
        initial_bank = 2000
        initial_nominal = 100

        # Получаем первый понедельник текущего месяца
        current_first_monday = NominalCalculator.get_first_monday_of_month(date)
        
        # Получаем первый понедельник предыдущего месяца
        prev_month = date.replace(day=1) - timedelta(days=1)
        prev_first_monday = NominalCalculator.get_first_monday_of_month(prev_month)

        # Получаем ставки за предыдущий месяц
        prev_month_bets = db.query(Bet).filter(
            Bet.date >= prev_first_monday,
            Bet.date < current_first_monday
        ).all()

        if not prev_month_bets:
            return initial_nominal

        # Считаем профит за предыдущий месяц
        total_profit = sum(bet.profit for bet in prev_month_bets)
        
        if total_profit <= 0:
            # Если месяц убыточный, оставляем прежний номинал
            return db.query(Bet).filter(
                Bet.date < prev_first_monday
            ).order_by(Bet.date.desc()).first().nominal or initial_nominal
        
        # Увеличиваем банк на треть прибыли
        profit_addition = total_profit / 3
        new_bank = initial_bank + profit_addition
        
        # Новый номинал - 5% от нового банка
        new_nominal = round(new_bank * 0.05, 2)
        
        return new_nominal