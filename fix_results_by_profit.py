from app.database.database import SessionLocal
from app.models.bet import Bet

def fix_results_by_profit():
    db = SessionLocal()
    
    bets = db.query(Bet).all()
    wins_count = 0
    losses_count = 0
    no_result_count = 0
    
    print("Исправляем результаты на основе профита...")
    
    for bet in bets:
        if bet.profit is not None and bet.profit != 0:
            if bet.profit > 0:
                # Положительный профит = выигрыш
                bet.won = True
                bet.result = "WIN"
                wins_count += 1
            elif bet.profit < 0:
                # Отрицательный профит = проигрыш
                bet.won = False
                bet.result = "LOSE"
                losses_count += 1
        else:
            no_result_count += 1
    
    db.commit()
    
    print(f"\n=== РЕЗУЛЬТАТЫ ИСПРАВЛЕНИЯ ===")
    print(f"Выигрышей: {wins_count}")
    print(f"Проигрышей: {losses_count}")
    print(f"Без результата: {no_result_count}")
    
    # Проверяем что получилось
    total = db.query(Bet).count()
    wins_db = db.query(Bet).filter(Bet.won == True).count()
    losses_db = db.query(Bet).filter(Bet.won == False).count()
    
    print(f"\n=== ПРОВЕРКА В БД ===")
    print(f"Всего записей: {total}")
    print(f"Побед в БД: {wins_db}")
    print(f"Поражений в БД: {losses_db}")
    
    # Проверяем несколько записей
    print(f"\n=== ПРИМЕРЫ ЗАПИСЕЙ ===")
    sample_bets = db.query(Bet).limit(5).all()
    for bet in sample_bets:
        print(f"ID: {bet.id}, Result: {bet.result}, Won: {bet.won}, Profit: {bet.profit}")
    
    db.close()

if __name__ == "__main__":
    fix_results_by_profit()