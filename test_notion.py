import os
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

def test_notion_data():
    token = os.getenv('NOTION_TOKEN_2024') or os.getenv('NOTION_TOKEN')
    database_id = os.getenv('NOTION_DATABASE_2024') or os.getenv('NOTION_DATABASE_ID')
    
    notion = Client(auth=token)
    
    # Получаем первые 5 записей
    response = notion.databases.query(
        database_id=database_id,
        page_size=5
    )
    
    print("=== ПРОВЕРКА ДАННЫХ ИЗ NOTION ===\n")
    
    for i, row in enumerate(response["results"], 1):
        properties = row["properties"]
        
        print(f"Запись {i}:")
        
        # Проверяем поле Результат
        if "Результат" in properties:
            result_prop = properties["Результат"]
            print(f"  Тип поля 'Результат': {result_prop['type']}")
            
            if result_prop['type'] == 'rich_text' and result_prop.get('rich_text'):
                for text_item in result_prop['rich_text']:
                    print(f"  Текст результата: '{text_item.get('plain_text', '')}'")
                    print(f"  Полный объект: {text_item}")
            elif result_prop['type'] == 'select' and result_prop.get('select'):
                print(f"  Select результат: '{result_prop['select'].get('name', '')}'")
            else:
                print(f"  Полное поле: {result_prop}")
        
        # Проверяем профит
        if "Потенциальный профит" in properties:
            profit_prop = properties["Потенциальный профит"]
            if profit_prop['type'] == 'number':
                print(f"  Профит: {profit_prop.get('number')}")
            elif profit_prop['type'] == 'formula':
                print(f"  Профит (формула): {profit_prop.get('formula', {}).get('number')}")
        
        print("---")

if __name__ == "__main__":
    test_notion_data()