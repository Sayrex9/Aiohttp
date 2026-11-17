from aiohttp import web
import hashlib
import jwt
from datetime import datetime, timedelta
import aiosqlite
from database import init_db, get_db

# Секретный ключ для JWT (в реальности хранится в переменных окружения)
SECRET_KEY = "my_super_secret_key_123"

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def get_current_user(request):
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None

    token = auth_header.replace('Bearer ', '')
    
    try:
        # Расшифровываем JWT токен
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("email")
    except jwt.ExpiredSignatureError:
        return None # Токен истек
    except jwt.InvalidTokenError:
        return None # Неверный токен

# --- ХЕНДЛЕРЫ ---

async def register(request):
    data = await request.json()
    if not data or 'email' not in data or 'password' not in data:
        return web.json_response({"error": "Нужны email и password"}, status=400)

    password_hash = hashlib.sha256(data['password'].encode()).hexdigest()

    db = await get_db()
    try:
        await db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", 
                         (data['email'], password_hash))
        await db.commit()

        cursor = await db.execute("SELECT id FROM users WHERE email = ?", (data['email'],))
        user_id = (await cursor.fetchone())[0]
        await cursor.close()

        return web.json_response({"id": user_id, "email": data['email']}, status=201)
    except aiosqlite.IntegrityError:
        return web.json_response({"error": "Пользователь уже существует"}, status=400)
    finally:
        await db.close()

async def login(request):
    data = await request.json()
    if not data or 'email' not in data or 'password' not in data:
        return web.json_response({"error": "Нужны email и password"}, status=400)

    password_hash = hashlib.sha256(data['password'].encode()).hexdigest()

    db = await get_db()
    cursor = await db.execute("SELECT id FROM users WHERE email = ? AND password_hash = ?",
                              (data['email'], password_hash))
    user = await cursor.fetchone()
    await cursor.close()
    await db.close()

    if user:
        # Генерируем JWT токен, который живет 1 час
        token = jwt.encode({
            "email": data['email'],
            "exp": datetime.utcnow() + timedelta(hours=1)
        }, SECRET_KEY, algorithm="HS256")
        
        return web.json_response({"token": token}, status=200)
    return web.json_response({"error": "Неверный логин или пароль"}, status=401)

async def create_ad(request):
    user_email = await get_current_user(request)
    if not user_email:
        return web.json_response({"error": "Требуется авторизация"}, status=401)

    data = await request.json()
    if not data or 'title' not in data:
        return web.json_response({"error": "Нужен заголовок"}, status=400)

    db = await get_db()
    
    cursor = await db.execute("SELECT id FROM users WHERE email = ?", (user_email,))
    owner_row = await cursor.fetchone()
    await cursor.close()

    if not owner_row:
        await db.close()
        return web.json_response({"error": "Пользователь не найден"}, status=401)

    owner_id = owner_row[0]

    await db.execute(
        "INSERT INTO advertisements (title, description, created_at, owner_id) VALUES (?, ?, ?, ?)",
        (data['title'], data.get('description', ''), datetime.now().isoformat(), owner_id)
    )
    await db.commit()

    cursor = await db.execute("SELECT last_insert_rowid()")
    ad_id = (await cursor.fetchone())[0]
    await cursor.close()
    await db.close()

    return web.json_response({"id": ad_id, "status": "created"}, status=201)

async def get_all_ads(request):
    db = await get_db()
    cursor = await db.execute("SELECT id, title, description, created_at, owner_id FROM advertisements")
    rows = await cursor.fetchall()
    await cursor.close()
    await db.close()

    ads = [{"id": r[0], "title": r[1], "description": r[2], "created_at": r[3], "owner_id": r[4]} for r in rows]
    return web.json_response(ads, status=200)

async def get_ad(request):
    ad_id = int(request.match_info['ad_id'])
    db = await get_db()
    cursor = await db.execute("SELECT id, title, description, created_at, owner_id FROM advertisements WHERE id = ?", (ad_id,))
    row = await cursor.fetchone()
    await cursor.close()
    await db.close()

    if not row:
        return web.json_response({"error": "Не найдено"}, status=404)

    ad = {"id": row[0], "title": row[1], "description": row[2], "created_at": row[3], "owner_id": row[4]}
    return web.json_response(ad, status=200)

async def update_ad(request):
    user_email = await get_current_user(request)
    if not user_email:
        return web.json_response({"error": "Требуется авторизация"}, status=401)

    ad_id = int(request.match_info['ad_id'])
    data = await request.json()

    db = await get_db()
    
    cursor = await db.execute("""
        SELECT a.id FROM advertisements a 
        JOIN users u ON a.owner_id = u.id 
        WHERE a.id = ? AND u.email = ?
    """, (ad_id, user_email))
    ad = await cursor.fetchone()
    await cursor.close()

    if not ad:
        await db.close()
        return web.json_response({"error": "Не найдено или нет прав"}, status=403)

    if 'title' in data:
        await db.execute("UPDATE advertisements SET title = ? WHERE id = ?", (data['title'], ad_id))
    if 'description' in data:
        await db.execute("UPDATE advertisements SET description = ? WHERE id = ?", (data['description'], ad_id))

    await db.commit()
    await db.close()
    return web.json_response({"status": "updated"}, status=200)

async def delete_ad(request):
    user_email = await get_current_user(request)
    if not user_email:
        return web.json_response({"error": "Требуется авторизация"}, status=401)

    ad_id = int(request.match_info['ad_id'])

    db = await get_db()
    
    cursor = await db.execute("""
        SELECT a.id FROM advertisements a
        JOIN users u ON a.owner_id = u.id
        WHERE a.id = ? AND u.email = ?
    """, (ad_id, user_email))
    ad = await cursor.fetchone()
    await cursor.close()

    if not ad:
        await db.close()
        return web.json_response({"error": "Не найдено или нет прав"}, status=403)

    await db.execute("DELETE FROM advertisements WHERE id = ?", (ad_id,))
    await db.commit()
    await db.close()
    return web.json_response({"status": "deleted"}, status=200)

# --- НАСТРОЙКА И ЗАПУСК ---

async def on_startup(app):
    await init_db()

app = web.Application()
app.on_startup.append(on_startup)

app.router.add_post('/register', register)
app.router.add_post('/login', login)
app.router.add_post('/advertisements', create_ad)
app.router.add_get('/advertisements', get_all_ads)
app.router.add_get('/advertisements/{ad_id}', get_ad)
app.router.add_patch('/advertisements/{ad_id}', update_ad)
app.router.add_delete('/advertisements/{ad_id}', delete_ad)

if __name__ == '__main__':
    web.run_app(app, host='127.0.0.1', port=8080)
