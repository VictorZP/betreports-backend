from fastapi import Header, FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import os, logging

from dotenv import load_dotenv
from sqlalchemy import text

from app.database.database import engine, SessionLocal, Base as DBBase, get_db
from app.models.bet import Base, Bet  # используем Base из моделей для create_all
from app.services.notion_sync import NotionSync
from app.services.profit_calculator import ProfitCalculator


# ===== env / init =====
load_dotenv()

# создаём таблицы при старте (на нужной БД)
Base.metadata.create_all(bind=engine)

logging.getLogger("uvicorn").info(f"PORT env = {os.getenv('PORT')}")

app = FastAPI(title="BetReports API")



ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
DEFAULT_SEASON = os.getenv("DEFAULT_SEASON", "2024")


# ===== health =====
@app.get("/api/health")
def health():
    return {"api": "ok"}

@app.get("/api/health/db")
def health_db():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"db": "ok"}


# ===== CORS =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== root =====
@app.get("/")
def read_root():
    return {"message": "BetReports API is running"}


# ===== Bets =====
@app.get("/api/bets")
def get_bets(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    bet_type: Optional[str] = None,
    is_premium: Optional[bool] = None,
    result: Optional[str] = None,
    month: Optional[str] = None,
    tournaments: Optional[str] = Query(None),
    limit: int = 10000,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Получение списка ставок с фильтрацией"""
    query = db.query(Bet)

    # Фильтр по месяцу YYYY-MM
    if month:
        year_s, month_s = month.split('-')
        year = int(year_s)
        month_num = int(month_s)
        from calendar import monthrange
        start_of_month = datetime(year, month_num, 1)
        last_day = monthrange(year, month_num)[1]
        end_of_month = datetime(year, month_num, last_day, 23, 59, 59)
        query = query.filter(Bet.date >= start_of_month, Bet.date <= end_of_month)

    # Диапазон дат (не применяем, если month задан)
    if start_date and not month:
        query = query.filter(Bet.date >= start_date)
    if end_date and not month:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Bet.date < end_dt)

    # Тип ставки
    if bet_type and bet_type != 'all':
        query = query.filter(Bet.bet_type.contains(bet_type))

    # Премиум
    if is_premium is not None:
        query = query.filter(Bet.is_premium == is_premium)

    # Результат
    if result and result != 'all':
        if result == 'WIN':
            query = query.filter(Bet.won == True)
        elif result == 'LOSE':
            query = query.filter(Bet.won == False)

    # Турниры
    if tournaments:
        tournament_list = tournaments.split(',')
        query = query.filter(Bet.tournament.in_(tournament_list))

    # Фильтр по времени
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

    # Сортировка и пагинация
    query = query.order_by(Bet.date.desc())
    bets = query.offset(offset).limit(limit).all()
    return bets


# ===== Stats =====
@app.get("/api/stats")
# ===== Stats =====
@app.get("/api/stats")
def get_stats(
    # даты
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    # время в дне
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    # фильтры
    bet_type: Optional[str] = None,
    is_premium: Optional[bool] = None,
    result: Optional[str] = None,           # NEW: WIN / LOSE / all
    month: Optional[str] = None,            # NEW: YYYY-MM
    season: Optional[str] = None,           # NEW: сезон
    tournaments: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Получение статистики с точными расчётами + корректная фильтрация:
    - month (YYYY-MM)
    - season
    - bet_type (contains, кроме 'all')
    - is_premium
    - result: WIN / LOSE (через Bet.won)
    - tournaments: CSV
    - start_date/end_date
    - start_time/end_time (доп. фильтрация по времени, не отключает остальные)
    """
    from calendar import monthrange

    query = db.query(Bet)

    # --- сезон ---
    if season:
        query = query.filter(Bet.season == season)

    # --- месяц YYYY-MM ---
    if month:
        try:
            year_s, month_s = month.split('-')
            year = int(year_s)
            month_num = int(month_s)
            start_of_month = datetime(year, month_num, 1)
            last_day = monthrange(year, month_num)[1]
            end_of_month = datetime(year, month_num, last_day, 23, 59, 59)
            query = query.filter(Bet.date >= start_of_month, Bet.date <= end_of_month)
        except Exception:
            pass  # некорректный формат - молча игнорируем

    # --- диапазон дат (если month не задан) ---
    if start_date and not month:
        query = query.filter(Bet.date >= start_date)
    if end_date and not month:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Bet.date < end_dt)

    # --- вид ставки ---
    if bet_type and bet_type != 'all':
        # используем contains как в /api/bets
        query = query.filter(Bet.bet_type.contains(bet_type))

    # --- премиум ---
    if is_premium is not None:
        query = query.filter(Bet.is_premium == is_premium)

    # --- результат ---
    if result and result != 'all':
        if result.upper() == 'WIN':
            query = query.filter(Bet.won == True)
        elif result.upper() == 'LOSE':
            query = query.filter(Bet.won == False)
        # прочее игнорируем

    # --- турниры (CSV) ---
    if tournaments:
        tournament_list = [t.strip() for t in tournaments.split(',') if t.strip()]
        if tournament_list:
            query = query.filter(Bet.tournament.in_(tournament_list))

    # Получаем предварительный список с учётом всех фильтров выше
    filtered_bets = query.all()

    # --- ДОП. фильтрация по времени внутри суток ---
    if start_time or end_time:
        def within_time(bet):
            if not bet.date:
                return False
            bt = bet.date.time()
            if start_time:
                st = datetime.strptime(start_time, "%H:%M").time()
                if bt < st:
                    return False
            if end_time:
                et = datetime.strptime(end_time, "%H:%M").time()
                if bt > et:
                    return False
            return True

        filtered_bets = [b for b in filtered_bets if within_time(b)]

    # ---- расчёт ----
    total_bets = len(filtered_bets)
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

    calculator = ProfitCalculator()
    profit_data = calculator.calculate_total_profit(filtered_bets)

    total_profit = profit_data["total_profit"]
    total_staked = profit_data["total_staked"]
    total_won = profit_data["total_won"]
    current_nominal = profit_data["current_nominal"]
    current_bank = profit_data["current_bank"]
    wins = profit_data["total_wins"]
    losses = profit_data["total_losses"]

    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

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
    """Разбивка по периодам"""
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
            "roi": round(
                (profit_data["total_profit"] / profit_data["total_staked"] * 100)
                if profit_data["total_staked"] > 0 else 0, 1
            )
        },
        "periods": profit_data["periods"]
    }


# ===== season data =====
@app.get("/api/season-data")
def get_season_data(season: str = "2024-2025", db: Session = Depends(get_db)):
    """Данные для выбранного сезона"""
    try:
        if season and season != "2024-2025":
            bets = db.query(Bet).filter(Bet.season == season).all()
        else:
            bets = db.query(Bet).all()

        tournaments = list(set([bet.tournament for bet in bets if bet.tournament]))
        tournaments.sort()

        dates = [bet.date for bet in bets if bet.date]
        min_date = min(dates).strftime("%Y-%m-%d") if dates else "2024-11-26"
        max_date = max(dates).strftime("%Y-%m-%d") if dates else datetime.now().strftime("%Y-%m-%d")

        months_dict = {}
        month_names = {
            1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
            5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
            9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
        }
        for bet in bets:
            if bet.date:
                month_key = bet.date.strftime("%Y-%m")
                months_dict[month_key] = f"{month_names[bet.date.month]} {bet.date.year}"

        months = [{"value": k, "label": v} for k, v in sorted(months_dict.items())]

        return {
            "tournaments": tournaments,
            "dateRange": {"min": min_date, "max": max_date},
            "months": months
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ===== sync =====
@app.post("/api/sync")
async def sync_data(
    season: str | None = Query(None),
    x_admin_token: str | None = Header(default=None, alias="X-ADMIN-TOKEN"),
    db: Session = Depends(get_db),
):
    # токен обязателен в проде
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # создаём синкер под сезон
    syncer = NotionSync(season=(season or DEFAULT_SEASON))

    # тяжёлая работа в пуле потоков
    result = await run_in_threadpool(syncer.sync_with_notion, db)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "Sync failed"))

    return result


# ===== прочие утилиты =====
@app.get("/api/test-db")
def test_database(db: Session = Depends(get_db)):
    """Тест соединения с БД"""
    try:
        count = db.query(Bet).count()
        return {"status": "connected", "bets_count": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/screenshot")
async def get_screenshot_proxy(url: str):
    """Прокси для получения скриншотов с prnt.sc"""
    import httpx
    from bs4 import BeautifulSoup

    try:
        if url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            return {"image_url": url}

        if 'prnt.sc' in url:
            async with httpx.AsyncClient() as client:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                response = await client.get(url, headers=headers, follow_redirects=True)
                soup = BeautifulSoup(response.text, 'html.parser')

                img_tag = soup.find('img', {'id': 'screenshot-image'}) or soup.find('img', class_='no-click screenshot-image')
                if img_tag and img_tag.get('src'):
                    img_url = img_tag['src']
                    if not img_url.startswith('http'):
                        img_url = 'https:' + img_url
                    return {"image_url": img_url}

        return {"image_url": url}
    except Exception as e:
        print(f"Error fetching screenshot: {e}")
        return {"image_url": None}


# ===== локальный запуск =====
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

    
