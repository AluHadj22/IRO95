# fix_enum_values.py
import sqlite3
import os

def fix_enum_values():
    db_path = os.path.join(os.path.dirname(__file__), "iro_courses.db")
    
    if not os.path.exists(db_path):
        print(f"База данных не найдена: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Проверяем и исправляем значения video_platform
    try:
        # Обновляем существующие записи
        cursor.execute("UPDATE courses SET video_platform = 'youtube' WHERE video_platform IS NULL")
        cursor.execute("UPDATE courses SET video_platform = 'youtube' WHERE video_platform = ''")
        print("✅ Обновлены значения video_platform")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # Проверяем и исправляем значения format_type
    try:
        cursor.execute("UPDATE courses SET format_type = 'online' WHERE format_type IS NULL")
        cursor.execute("UPDATE courses SET format_type = 'online' WHERE format_type = ''")
        print("✅ Обновлены значения format_type")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # Проверяем и исправляем значения is_open_ended
    try:
        cursor.execute("UPDATE courses SET is_open_ended = 0 WHERE is_open_ended IS NULL")
        print("✅ Обновлены значения is_open_ended")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    conn.commit()
    conn.close()
    print("\n🎉 Исправление данных завершено!")

if __name__ == "__main__":
    fix_enum_values()