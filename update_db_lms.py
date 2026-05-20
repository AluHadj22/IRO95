# update_db_lms.py
import sqlite3
import os

def update_database():
    db_path = os.path.join(os.path.dirname(__file__), "iro_courses.db")
    
    if not os.path.exists(db_path):
        print(f"База данных не найдена: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Создаём новые таблицы
    tables = [
        """
        CREATE TABLE IF NOT EXISTS course_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            order_index INTEGER DEFAULT 0,
            module_type VARCHAR(50) DEFAULT 'online',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS course_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            title VARCHAR(500) NOT NULL,
            content TEXT,
            video_url VARCHAR(500),
            order_index INTEGER DEFAULT 0,
            is_free BOOLEAN DEFAULT 0,
            duration_minutes INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (module_id) REFERENCES course_modules(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS lesson_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            filename VARCHAR(500) NOT NULL,
            file_url VARCHAR(500) NOT NULL,
            file_size INTEGER DEFAULT 0,
            file_type VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lesson_id) REFERENCES course_lessons(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS lesson_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            assignment_type VARCHAR(50) DEFAULT 'text',
            max_score INTEGER DEFAULT 100,
            passing_score INTEGER DEFAULT 60,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lesson_id) REFERENCES course_lessons(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS assignment_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            question_image VARCHAR(500),
            question_video VARCHAR(500),
            question_type VARCHAR(50) DEFAULT 'text',
            options TEXT,
            correct_answer TEXT,
            points INTEGER DEFAULT 10,
            order_index INTEGER DEFAULT 0,
            FOREIGN KEY (assignment_id) REFERENCES lesson_assignments(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_module_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            module_id INTEGER NOT NULL,
            is_completed BOOLEAN DEFAULT 0,
            completed_by_teacher BOOLEAN DEFAULT 0,
            completed_at DATETIME,
            teacher_comment TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (module_id) REFERENCES course_modules(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_lesson_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            is_completed BOOLEAN DEFAULT 0,
            completed_at DATETIME,
            last_position INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (lesson_id) REFERENCES course_lessons(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS assignment_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            score INTEGER,
            is_passed BOOLEAN DEFAULT 0,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            graded_by INTEGER,
            graded_at DATETIME,
            teacher_comment TEXT,
            FOREIGN KEY (assignment_id) REFERENCES lesson_assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (graded_by) REFERENCES users(id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT,
            answer_file VARCHAR(500),
            is_correct BOOLEAN DEFAULT 0,
            points_earned INTEGER DEFAULT 0,
            FOREIGN KEY (submission_id) REFERENCES assignment_submissions(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES assignment_questions(id) ON DELETE CASCADE
        )
        """
    ]
    
    for table_sql in tables:
        try:
            cursor.execute(table_sql)
            print(f"✅ Таблица создана/проверена")
        except Exception as e:
            print(f"Ошибка: {e}")
    
    conn.commit()
    conn.close()
    print("\n🎉 Обновление базы данных LMS завершено!")

if __name__ == "__main__":
    update_database()