from typing import List, Dict, Any
from datetime import datetime, timedelta
from app.models.bet import Bet

class ProfitCalculator:
    def __init__(self):
        self.initial_bank = 2000
        self.initial_nominal = 100
        self.max_nominal = 1000  # Максимальный номинал
        
    def get_first_monday(self, year, month):
        """Получить первый понедельник месяца"""
        first_day = datetime(year, month, 1)
        days_until_monday = (7 - first_day.weekday()) % 7
        if days_until_monday == 0 and first_day.weekday() != 0:
            days_until_monday = 7
        return first_day + timedelta(days=days_until_monday)
    
    def calculate_nominal(self, bank):
        """Рассчитать номинал с учетом максимального значения"""
        nominal = round(bank * 0.05)
        # Ограничиваем максимальным значением
        if nominal > self.max_nominal:
            nominal = self.max_nominal
        # Минимальный номинал 100
        if nominal < 100:
            nominal = 100
        return nominal
    
    def calculate_total_profit(self, bets: List[Bet]) -> Dict[str, Any]:
        """Расчет профита с пересчетом номинала каждый первый понедельник месяца"""
        
        if not bets:
            return {
                "total_profit": 0,
                "total_staked": 0,
                "total_won": 0,
                "total_wins": 0,
                "total_losses": 0,
                "current_nominal": self.initial_nominal,
                "current_bank": self.initial_bank,
                "periods": []
            }
        
        # Сортируем ставки по дате
        sorted_bets = sorted(bets, key=lambda x: x.date if x.date else datetime.min)
        
        # Начинаем с первой даты в данных
        start_date = sorted_bets[0].date
        end_date = sorted_bets[-1].date
        
        print(f"Период данных: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        
        # Инициализация
        current_bank = self.initial_bank
        current_nominal = self.initial_nominal
        total_profit = 0
        total_staked = 0
        total_won = 0
        total_wins = 0
        total_losses = 0
        periods = []
        previous_month_profit = 0
        
        # Находим первый понедельник после начала данных
        current_date = start_date
        period_start = start_date
        
        while current_date <= end_date:
            # Находим следующий первый понедельник
            if current_date.month == 12:
                next_year = current_date.year + 1
                next_month = 1
            else:
                next_year = current_date.year
                next_month = current_date.month + 1
            
            next_first_monday = self.get_first_monday(next_year, next_month)
            
            # Конец периода - день перед следующим первым понедельником
            period_end = min(next_first_monday - timedelta(days=1), end_date)
            
            # Собираем ставки текущего периода
            period_bets = [bet for bet in sorted_bets 
                          if bet.date and period_start <= bet.date <= period_end]
            
            if period_bets:
                # Считаем профит периода
                period_profit = 0
                period_staked = 0
                period_wins = 0
                period_losses = 0
                
                for bet in period_bets:
                    stake = current_nominal
                    period_staked += stake
                    total_staked += stake
                    
                    if bet.won is True:
                        # Выигрыш = ставка * 0.85
                        win_amount = stake * 0.85
                        period_profit += win_amount
                        total_profit += win_amount
                        total_won += stake + win_amount  # Возврат ставки + выигрыш
                        period_wins += 1
                        total_wins += 1
                    elif bet.won is False:
                        # Проигрыш = потеря всей ставки
                        period_profit -= stake
                        total_profit -= stake
                        period_losses += 1
                        total_losses += 1
                
                # Сохраняем данные периода
                period_data = {
                    "start": period_start.strftime("%Y-%m-%d"),
                    "end": period_end.strftime("%Y-%m-%d"),
                    "month": period_start.strftime("%Y-%m"),
                    "bets": len(period_bets),
                    "wins": period_wins,
                    "losses": period_losses,
                    "profit": round(period_profit, 2),
                    "staked": round(period_staked, 2),
                    "nominal": current_nominal,
                    "bank": round(current_bank, 2),
                    "win_rate": round(period_wins / len(period_bets) * 100, 1) if period_bets else 0
                }
                periods.append(period_data)
                
                print(f"\nПериод {period_start.strftime('%Y-%m-%d')} - {period_end.strftime('%Y-%m-%d')}")
                print(f"  Номинал: ${current_nominal}")
                print(f"  Ставок: {len(period_bets)} (W: {period_wins}, L: {period_losses})")
                print(f"  Профит: ${period_profit:.2f}")
                
                # Пересчет для следующего периода (если это не последний период)
                if period_end < end_date:
                    if period_profit > 0:
                        # Прибыльный месяц: добавляем 1/3 профита к банку
                        bank_addition = period_profit / 3
                        current_bank += bank_addition
                        new_nominal = self.calculate_nominal(current_bank)
                        
                        print(f"  -> Прибыльный: добавка к банку ${bank_addition:.2f}")
                        print(f"  -> Новый банк: ${current_bank:.2f}")
                        print(f"  -> Новый номинал: ${new_nominal}" + 
                              (" (ограничен максимумом)" if new_nominal == self.max_nominal else ""))
                        
                        current_nominal = new_nominal
                        previous_month_profit = period_profit
                    else:
                        # Убыточный месяц
                        print(f"  -> Убыточный: банк и номинал не меняются")
                        
                        # Проверка суммы с предыдущим месяцем
                        if previous_month_profit < 0:
                            combined = period_profit + previous_month_profit
                            if combined > 0:
                                bank_addition = combined / 3
                                current_bank += bank_addition
                                new_nominal = self.calculate_nominal(current_bank)
                                print(f"  -> Сумма с предыдущим месяцем > 0: добавка ${bank_addition:.2f}")
                                print(f"  -> Новый номинал: ${new_nominal}")
                                current_nominal = new_nominal
                        
                        previous_month_profit = period_profit
            
            # Переход к следующему периоду
            if next_first_monday > end_date:
                break
            
            current_date = next_first_monday
            period_start = next_first_monday
        
        # Финальный расчет банка
        final_bank = self.initial_bank
        for period in periods:
            if period['profit'] > 0:
                final_bank += period['profit'] / 3
        
        print(f"\n=== ИТОГОВАЯ СТАТИСТИКА ===")
        print(f"Всего ставок: {total_wins + total_losses}")
        print(f"Побед: {total_wins}, Поражений: {total_losses}")
        print(f"Процент побед: {total_wins / (total_wins + total_losses) * 100:.1f}%")
        print(f"Общий профит: ${total_profit:.2f}")
        print(f"Финальный банк: ${final_bank:.2f}")
        print(f"Финальный номинал: ${current_nominal}")
        print(f"ROI: {(total_profit / total_staked * 100):.1f}%")
        
        return {
            "total_profit": round(total_profit, 2),
            "total_staked": round(total_staked, 2),
            "total_won": round(total_won, 2),
            "total_wins": total_wins,
            "total_losses": total_losses,
            "current_nominal": current_nominal,
            "current_bank": round(final_bank, 2),
            "periods": periods
        }