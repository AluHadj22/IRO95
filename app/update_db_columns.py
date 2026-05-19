# update_db_columns.py
from sqlalchemy import text
from app.database import engine

def update_database():
    with engine.connect() as conn:
        # Добавляем новые колонки
        try:
            conn.execute(text("ALTER TABLE courses ADD COLUMN format_type VARCHAR(50) DEFAULT 'online'"))
            print("Добавлена колонка format_type")
        except Exception as e:
            print(f"Колонка format_type уже существует: {e}")
        
        try:
            conn.execute(text("ALTER TABLE courses ADD COLUMN video_platform VARCHAR(50) DEFAULT 'youtube'"))
            print("Добавлена колонка video_platform")
        except Exception as e:
            print(f"Колонка video_platform уже существует: {e}")
        
        try:
            conn.execute(text("ALTER TABLE courses ADD COLUMN is_open_ended BOOLEAN DEFAULT FALSE"))
            print("Добавлена колонка is_open_ended")
        except Exception as e:
            print(f"Колонка is_open_ended уже существует: {e}")
        
        conn.commit()
        print("Обновление базы данных завершено!")

if __name__ == "__main__":
    update_database()