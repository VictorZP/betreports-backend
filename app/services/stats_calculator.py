from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from ..models.bet import Bet
from ..services.nominal_calculator import NominalCalculator

class StatsCalculator:
    @staticmethod
    def calculate_stats(db: Session, filters: Dict = None) -> Dict:
        """Рассчитывает статистику по ставкам"""
        query = db.query(Bet)
        
        # Применяем фильтры
        if filters:
            if filters.get('start_date'):
                query = query.filter(Bet.date >= filters['start_date'])
            if filters.get('end_date'):
                query = query.filter(Bet.date <= filters['end_date'])
            if filters.get('tournaments'):
                query = query.filter(Bet.tournament.in_(filters['tournaments']))
            if filters.get('bet_type'):
                query = query.filter(Bet.bet_type == filters['bet_type'])
            if filters.get('is_premium') is not None:
                query = query.filter(Bet.is_premium == filters['is_premium'])
        
        bets = query.all()
        
        if not bets:
            return {
                'total_bets': 0,
                'win_rate': 0,
                'total_profit': 0,
                'roi': 0,
                'current_nominal': 100,
                'current_bank': 2000
            }
        
        # Подсчет статистики
        total_bets = len(bets)
        wins = sum(1 for bet in bets if bet.result == 'WIN')
        win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
        
        # Расчет профита с учетом номинала
        total_profit = 0
        total_staked = 0
        
        for bet in bets:
            # Получаем номинал для месяца ставки
            nominal = NominalCalculator.calculate_monthly_nominal(db, bet.date)
            bet.nominal = nominal
            
            if bet.result == 'WIN':
                profit = nominal * 0.85
            elif bet.result == 'LOSE':
                profit = -nominal
            else:
                profit = 0
            
            bet.profit = profit
            total_profit += profit
            total_staked += nominal
        
        roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
        
        # Получаем текущий номинал и банк
        current_date = datetime.now()
        current_nominal = NominalCalculator.calculate_monthly_nominal(db, current_date)
        
        # Расчет текущего банка
        initial_bank = 2000
        current_bank = initial_bank
        
        # Группируем ставки по месяцам и пересчитываем банк
        first_monday = NominalCalculator.get_first_monday_of_month(datetime(2024, 9, 1))
        current_first_monday = NominalCalculator.get_first_monday_of_month(current_date)
        
        while first_monday < current_first_monday:
            next_first_monday = NominalCalculator.get_first_monday_of_month(
                (first_monday + timedelta(days=32)).replace(day=1)
            )
            
            month_bets = [b for b in bets if first_monday <= b.date < next_first_monday]
            month_profit = sum(b.profit for b in month_bets)
            
            if month_profit > 0:
                current_bank += month_profit / 3
            
            first_monday = next_first_monday
        
        return {
            'total_bets': total_bets,
            'win_rate': round(win_rate, 1),
            'total_profit': round(total_profit, 2),
            'roi': round(roi, 1),
            'current_nominal': round(current_nominal, 2),
            'current_bank': round(current_bank, 2)
        }