import sqlite3
import os

DB_FOLDER = './data'
DB_PATH = os.path.join(DB_FOLDER, 'kokoro_journey.db')

def init_db():

    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                company TEXT,
                release_date TEXT
            );
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS play_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_seconds INTEGER,
                FOREIGN KEY(game_id) REFERENCES games(id)
            );
            ''')
        print("数据库初始化/验证成功。")
    except sqlite3.Error as e:
        print(f"数据库初始化失败: {e}")
        exit(1)


def select_all_games():
    try:
        with sqlite3.connect(DB_PATH) as conn:
           
            cursor = conn.cursor()
            
            conn.row_factory = sqlite3.Row 
            
            cursor.execute("SELECT * FROM games ORDER BY name;")
            rows = cursor.fetchall()
           
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"查询 games 表失败: {e}")
        return [] 
def get_or_create_game(name: str) -> int | None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM games WHERE name = ?;", (name,))
            result = cursor.fetchone()
            
            if result:
                return result[0] 
            else:
                cursor.execute("INSERT INTO games (name) VALUES (?);", (name,))
                return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"获取或创建游戏 '{name}' 失败: {e}")
        return None
