from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from sqlalchemy import text
from app.database.database import engine, SessionLocal, Base, get_db
from app.models.bet import Base, Bet
from app.services.notion_sync import NotionSync  # Изменено: импортируем класс
from app.services.profit_calculator import ProfitCalculator
from fastapi import Header

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

def require_admin(x_admin_token: str = Header(None)):
    # чтобы не забыть задать токен в переменных окружения Railway
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN is not configured on the server")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    return True

# Загрузка переменных окружения
load_dotenv()

# Создание таблиц
Base.metadata.create_all(bind=engine)

app = FastAPI(title="BetReports API")

@app.get("/api/health")
def health():
    return {"api": "ok"}

@app.get("/api/health/db")
def health_db():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"db": "ok"}

notion_sync = NotionSync ()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "https://frontend-production-0d68.up.railway.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "BetReports API is running"}

@app.get("/api/bets")
def get_bets(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    bet_type: Optional[str] = None,
    is_premium: Optional[bool] = None,
    result: Optional[str] = None,  # Добавлено
    month: Optional[str] = None,  # Добавлено
    tournaments: Optional[str] = Query(None),
    limit: int = 10000,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Получение списка ставок с фильтрацией"""
    query = db.query(Bet)
    
    # Фильтрация по месяцу
    if month:
        # month приходит в формате "2024-11"
        year, month_num = month.split('-')
        year = int(year)
        month_num = int(month_num)
        
        # Начало и конец месяца
        from calendar import monthrange
        start_of_month = datetime(year, month_num, 1)
        last_day = monthrange(year, month_num)[1]
        end_of_month = datetime(year, month_num, last_day, 23, 59, 59)
        
        query = query.filter(Bet.date >= start_of_month, Bet.date <= end_of_month)
    
    # Остальные фильтры
    if start_date and not month:  # Не применяем если уже есть фильтр по месяцу
        query = query.filter(Bet.date >= start_date)
    if end_date and not month:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Bet.date < end_dt)
    
    # Фильтрация по типу ставки (OVER/UNDER)
    if bet_type and bet_type != 'all':
        query = query.filter(Bet.bet_type.contains(bet_type))
    
    # Фильтрация по премиум
    if is_premium is not None:
        query = query.filter(Bet.is_premium == is_premium)
    
    # Фильтрация по результату
    if result and result != 'all':
        if result == 'WIN':
            query = query.filter(Bet.won == True)
        elif result == 'LOSE':
            query = query.filter(Bet.won == False)
    
    # Фильтрация по турнирам
    if tournaments:
        tournament_list = tournaments.split(',')
        query = query.filter(Bet.tournament.in_(tournament_list))
    
    # Фильтрация по времени
    if start_time or end_time:
        bets_list = query.all()
        filtered_bets = []
        for bet in bets_list:
            if bet.date:
                bet_time = bet.date.time()
                if start_time:
                    start_time_obj = datetime.strptime(start_time, "%H:%M").time()
                    if bet_time < start_time_obj:
                        continue
                if end_time:
                    end_time_obj = datetime.strptime(end_time, "%H:%M").time()
                    if bet_time > end_time_obj:
                        continue
                filtered_bets.append(bet)
        return filtered_bets[:limit]
    
    # Сортировка по дате (новые первые)
    query = query.order_by(Bet.date.desc())
    
    # Пагинация
    bets = query.offset(offset).limit(limit).all()
    
    return bets

@app.get("/api/stats")
def get_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    bet_type: Optional[str] = None,
    is_premium: Optional[bool] = None,
    tournaments: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Получение статистики с точными расчетами"""
    query = db.query(Bet)
    
    # Применяем фильтры
    if start_date:
        query = query.filter(Bet.date >= start_date)
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Bet.date < end_dt)
    
    
    # Фильтрация по времени
    if start_time or end_time:
        bets_list = query.all()
        filtered_bets = []
        for bet in bets_list:
            if bet.date:
                bet_time = bet.date.time()
                if start_time:
                    start_time_obj = datetime.strptime(start_time, "%H:%M").time()
                    if bet_time < start_time_obj:
                        continue
                if end_time:
                    end_time_obj = datetime.strptime(end_time, "%H:%M").time()
                    if bet_time > end_time_obj:
                        continue
                filtered_bets.append(bet)
        bets = filtered_bets
    else:
        if bet_type:
            query = query.filter(Bet.bet_type == bet_type)
        if is_premium is not None:
            query = query.filter(Bet.is_premium == is_premium)
        if tournaments:
            tournament_list = tournaments.split(',')
            query = query.filter(Bet.tournament.in_(tournament_list))
        bets = query.all()
    
    # Расчет статистики
    total_bets = len(bets)
    
    if total_bets == 0:
        return {
            "totalBets": 0,
            "winRate": 0.0,
            "totalProfit": 0.0,
            "totalStaked": 0.0,
            "totalWon": 0.0,
            "roi": 0.0,
            "wins": 0,
            "losses": 0,
            "currentNominal": 100,
            "currentBank": 2000
        }
    
    # Используем калькулятор для точных расчетов
    calculator = ProfitCalculator()
    profit_data = calculator.calculate_total_profit(bets)
    
    total_profit = profit_data["total_profit"]
    total_staked = profit_data["total_staked"]
    total_won = profit_data["total_won"]
    current_nominal = profit_data["current_nominal"]
    current_bank = profit_data["current_bank"]
    wins = profit_data["total_wins"]
    losses = profit_data["total_losses"]
    
    # Процент побед
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    
    # ROI = (чистая прибыль / сумма всех ставок) * 100
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    
    print(f"=== ТОЧНАЯ СТАТИСТИКА ===")
    print(f"Всего ставок: {total_bets}")
    print(f"Побед: {wins}, Поражений: {losses}")
    print(f"Процент побед: {win_rate:.1f}%")
    print(f"Точная сумма всех ставок: ${total_staked:.2f}")
    print(f"Точная сумма всех выигрышей: ${total_won:.2f}")
    print(f"Чистая прибыль: ${total_profit:.2f}")
    print(f"ROI: {roi:.1f}%")
    print(f"Текущий номинал: ${current_nominal:.2f}")
    print(f"Текущий банк: ${current_bank:.2f}")
    print("========================")
    
    return {
        "totalBets": total_bets,
        "winRate": round(win_rate, 1),
        "totalProfit": round(total_profit, 2),
        "totalStaked": round(total_staked, 2),
        "totalWon": round(total_won, 2),
        "roi": round(roi, 1),
        "wins": wins,
        "losses": losses,
        "currentNominal": current_nominal,
        "currentBank": current_bank
    }

@app.get("/api/stats/periods")
def get_periods_breakdown(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Получение детальной разбивки по периодам"""
    query = db.query(Bet)
    
    if start_date:
        query = query.filter(Bet.date >= start_date)
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Bet.date < end_dt)
    
    bets = query.all()
    
    calculator = ProfitCalculator()
    profit_data = calculator.calculate_total_profit(bets)
    
    return {
        "summary": {
            "total_profit": profit_data["total_profit"],
            "total_staked": profit_data["total_staked"],
            "total_won": profit_data["total_won"],
            "roi": round((profit_data["total_profit"] / profit_data["total_staked"] * 100) if profit_data["total_staked"] > 0 else 0, 1)
        },
        "periods": profit_data["periods"]
    }

@app.get("/api/debug/check-results")
def check_results(db: Session = Depends(get_db)):
    """Проверка результатов и расчета профита для отладки"""
    bets = db.query(Bet).limit(20).all()
    
    debug_info = []
    total_calc_profit = 0
    
    for bet in bets:
        stake = float(bet.stake) if bet.stake else 100.0
        calculated_profit = 0
        is_win = None
        
        if bet.result:
            result_str = str(bet.result).strip().upper()
            if any(win_marker in result_str for win_marker in ['WIN', 'W', 'ПОБЕДА', '✅', 'ВЫИГРЫШ', 'WON']):
                is_win = True
                calculated_profit = stake * 0.85  # Профит при коэфф 1.85
            elif any(loss_marker in result_str for loss_marker in ['LOSS', 'L', 'ПРОИГРЫШ', '❌', 'LOST', 'LOSE']):
                is_win = False
                calculated_profit = -stake
        
        total_calc_profit += calculated_profit
        
        info = {
            "id": bet.id,
            "date": str(bet.date)[:10] if bet.date else None,
            "match": bet.match,
            "bet": f"{bet.bet_type} {bet.total_value}",
            "result": bet.result,
            "stored_profit": bet.profit,
            "nominal": stake,
            "is_win": is_win,
            "calculated_profit": round(calculated_profit, 2),
            "running_total": round(total_calc_profit, 2)
        }
        
        debug_info.append(info)
    
    return {
        "bets": debug_info,
        "summary": {
            "total_calculated_profit": round(total_calc_profit, 2),
            "bet_count": len(debug_info)
        }
    }

@app.get("/api/debug/monthly-breakdown")
def get_monthly_breakdown(db: Session = Depends(get_db)):
    """Детальная разбивка расчетов по месяцам для проверки"""
    bets = db.query(Bet).order_by(Bet.date).all()
    
    calculator = ProfitCalculator()
    profit_data = calculator.calculate_total_profit(bets)
    
    # Форматируем для удобного просмотра
    monthly_stats = []
    for period in profit_data["periods"]:
        monthly_stats.append({
            "period": f"{period['start'][:10]} - {period['end'][:10]}",
            "nominal": f"${period['nominal']:.2f}",
            "bank": f"${period['bank']:.2f}",
            "bets": period['bets'],
            "wins": period['wins'],
            "losses": period['losses'],
            "profit": f"${period['profit']:.2f}",
            "total_staked": f"${period['staked']:.2f}",
            "running_total": f"${period['total_profit']:.2f}"
        })
    
    return {
        "monthly_breakdown": monthly_stats,
        "final_stats": {
            "total_profit": f"${profit_data['total_profit']:.2f}",
            "total_staked": f"${profit_data['total_staked']:.2f}",
            "final_nominal": f"${profit_data['current_nominal']:.2f}",
            "final_bank": f"${profit_data['current_bank']:.2f}",
            "roi": f"{(profit_data['total_profit'] / profit_data['total_staked'] * 100):.1f}%"
        }
    }

@app.get("/api/tournaments")
def get_tournaments(db: Session = Depends(get_db)):
    """Получение списка всех турниров"""
    tournaments = db.query(Bet.tournament).distinct().filter(Bet.tournament.isnot(None)).all()
    return sorted([t[0] for t in tournaments if t[0]])

@app.get("/api/season-data")
def get_season_data(season: str = "2024-2025", db: Session = Depends(get_db)):
    """Получение данных для выбранного сезона"""
    try:
        # Получаем все ставки
        if season and season != "2024-2025":
            bets = db.query(Bet).filter(Bet.season == season).all()
        else:
            # Для текущего сезона берем все ставки (пока у нас нет поля season у всех записей)
            bets = db.query(Bet).all()
        
        # Собираем уникальные турниры
        tournaments = list(set([bet.tournament for bet in bets if bet.tournament]))
        tournaments.sort()
        
        # Определяем диапазон дат
        dates = [bet.date for bet in bets if bet.date]
        min_date = min(dates).strftime("%Y-%m-%d") if dates else "2024-11-26"
        max_date = max(dates).strftime("%Y-%m-%d") if dates else datetime.now().strftime("%Y-%m-%d")
        
        # Собираем доступные месяцы
        months_dict = {}
        for bet in bets:
            if bet.date:
                month_key = bet.date.strftime("%Y-%m")
                # Русские названия месяцев
                month_names = {
                    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
                    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
                    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
                }
                month_name = f"{month_names[bet.date.month]} {bet.date.year}"
                months_dict[month_key] = month_name
        
        # Сортируем месяцы по дате
        months = [{"value": k, "label": v} for k, v in sorted(months_dict.items())]
        
        print(f"Found {len(tournaments)} tournaments and {len(months)} months")
        print(f"Months: {months}")
        
        return {
            "tournaments": tournaments,
            "dateRange": {"min": min_date, "max": max_date},
            "months": months
        }
    except Exception as e:
        print(f"Error in get_season_data: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import Query

@app.post("/api/sync")
async def sync_data(
    season: str = Query(default="2024-2025", regex=r"^\d{4}-\d{4}$"),
    admin_token: str | None = Header(default=None, alias="X-ADMIN-TOKEN"),
):
    # 1) проверяем токен
    expected = os.getenv("ADMIN_TOKEN")
    if expected and admin_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2) вызываем синхронизацию (в пуле потоков, чтобы не блокировать)
    stats = await run_in_threadpool(notion_sync.sync, season)

    # 3) отвечаем как раньше
    return {
        "success": True,
        "message": "Синхронизация завершена успешно",
        "stats": stats,
    }

# Проверочный эндпоинт
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/screenshot")
async def get_screenshot_proxy(url: str):
    """Прокси для получения скриншотов с prnt.sc"""
    import httpx
    from bs4 import BeautifulSoup
    
    try:
        # Если это уже прямая ссылка на изображение
        if url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            return {"image_url": url}
        
        # Для prnt.sc ссылок
        if 'prnt.sc' in url:
            async with httpx.AsyncClient() as client:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = await client.get(url, headers=headers, follow_redirects=True)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Ищем изображение на странице
                img_tag = soup.find('img', {'id': 'screenshot-image'})
                if img_tag and img_tag.get('src'):
                    img_url = img_tag['src']
                    if not img_url.startswith('http'):
                        img_url = 'https:' + img_url
                    return {"image_url": img_url}
                
                # Альтернативный поиск
                img_tag = soup.find('img', class_='no-click screenshot-image')
                if img_tag and img_tag.get('src'):
                    img_url = img_tag['src']
                    if not img_url.startswith('http'):
                        img_url = 'https:' + img_url
                    return {"image_url": img_url}
        
        return {"image_url": url}
        
    except Exception as e:
        print(f"Error fetching screenshot: {e}")
        return {"image_url": None}

@app.get("/api/test-db")
def test_database(db: Session = Depends(get_db)):
    """Тестирование подключения к БД"""
    try:
        count = db.query(Bet).count()
        return {
            "status": "connected",
            "bets_count": count
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/api/debug/nominal-periods")
def get_nominal_periods(db: Session = Depends(get_db)):
    """Детальный просмотр периодов и пересчетов номинала"""
    bets = db.query(Bet).order_by(Bet.date).all()
    
    calculator = ProfitCalculator()
    result = calculator.calculate_total_profit(bets)
    
    detailed_periods = []
    running_bank = 2000
    
    for i, period in enumerate(result["periods"]):
        bank_change = 0
        if period['profit'] > 0:
            bank_change = period['profit'] / 3
            running_bank += bank_change
        
        detailed_periods.append({
            "period": f"{period['start']} - {period['end']}",
            "month": period['month'],
            "bets": period['bets'],
            "wins": period['wins'],
            "losses": period['losses'],
            "nominal": f"${period['nominal']:.0f}",
            "period_profit": f"${period['profit']:.2f}",
            "bank_addition": f"${bank_change:.2f}" if bank_change > 0 else "-",
            "bank_after": f"${running_bank:.2f}",
            "next_nominal": f"${round(running_bank * 0.05):.0f}" if i < len(result['periods'])-1 else "-"
        })
    
    return {
        "periods": detailed_periods,
        "summary": {
            "initial_bank": "$2000",
            "final_bank": f"${result['current_bank']:.2f}",
            "initial_nominal": "$100",
            "final_nominal": f"${result['current_nominal']:.0f}",
            "total_profit": f"${result['total_profit']:.2f}",
            "roi": f"{(result['total_profit'] / result['total_staked'] * 100):.1f}%"
        }
    }

@app.get("/health")
def health():
    return {"api": "ok"}

@app.get("/health/db")
def health_db():
    # просто проверяем, что БД отвечает
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"db": "ok"}    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

