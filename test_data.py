from app.database.database import SessionLocal
from app.models.bet import Bet

def check_bets_data():
    db = SessionLocal()
    
    # Проверяем первые 10 записей
    bets = db.query(Bet).limit(10).all()
    
    print("=== ПРОВЕРКА ДАННЫХ В БД ===")
    for bet in bets:
        print(f"ID: {bet.id}")
        print(f"  Результат (result): {bet.result}")
        print(f"  Won: {bet.won}")
        print(f"  Profit: {bet.profit}")
        print(f"  Stake: {bet.stake}")
        print("---")
    
    # Считаем статистику
    total = db.query(Bet).count()
    wins = db.query(Bet).filter(Bet.won == True).count()
    losses = db.query(Bet).filter(Bet.won == False).count()
    no_result = db.query(Bet).filter(Bet.won == None).count()
    
    print(f"\n=== СТАТИСТИКА ===")
    print(f"Всего: {total}")
    print(f"Побед (won=True): {wins}")
    print(f"Поражений (won=False): {losses}")
    print(f"Без результата (won=None): {no_result}")
    
    db.close()

if __name__ == "__main__":
    check_bets_data()