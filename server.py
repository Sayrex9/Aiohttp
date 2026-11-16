# server.py
from aiohttp import web
import hashlib
from datetime import datetime

# --- НАША БАЗА ДАННЫХ (как в Flask) ---
users_db = {}
ads_db = {}
tokens = {}
user_id_counter = 1
ad_id_counter = 1


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def generate_token(email):
    return hashlib.md5(email.encode()).hexdigest()


async def get_current_user(request):
    """В aiohttp заголовки достаются из request"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None
    token = auth_header.replace('Bearer ', '')
    return tokens.get(token)

# --- ХЕНДЛЕРЫ (ФУНКЦИИ РОУТОВ) ---


# Регистрация
async def register(request):
    global user_id_counter
    data = await request.json()  # В aiohttp нужно писать await перед чтением тела!

    if not data or 'email' not in data or 'password' not in data:
        return web.json_response({"error": "Нужны email и password"}, status=400)

    password_hash = hashlib.sha256(data['password'].encode()).hexdigest()

    users_db[user_id_counter] = {
        "id": user_id_counter,
        "email": data['email'],
        "password_hash": password_hash
    }
    user_id_counter += 1
    return web.json_response({"id": user_id_counter - 1, "email": data['email']}, status=201)


# Логин
async def login(request):
    data = await request.json()
    if not data or 'email' not in data or 'password' not in data:
        return web.json_response({"error": "Нужны email и password"}, status=400)

    password_hash = hashlib.sha256(data['password'].encode()).hexdigest()

    for user_id, user in users_db.items():
        if user['email'] == data['email'] and user['password_hash'] == password_hash:
            token = generate_token(data['email'])
            tokens[token] = user_id
            return web.json_response({"token": token}, status=200)

    return web.json_response({"error": "Неверный логин или пароль"}, status=401)


# Создание объявления (POST)
async def create_ad(request):
    global ad_id_counter
    user_id = await get_current_user(request)
    if not user_id:
        return web.json_response({"error": "Требуется авторизация"}, status=401)

    data = await request.json()
    if not data or 'title' not in data:
        return web.json_response({"error": "Нужен заголовок"}, status=400)

    ads_db[ad_id_counter] = {
        "id": ad_id_counter,
        "title": data['title'],
        "description": data.get('description', ''),
        "created_at": datetime.now().isoformat(),
        "owner_id": user_id
    }
    ad_id_counter += 1
    return web.json_response({
        "id": ad_id_counter - 1,
        "status": "created"},
        status=201
        )


# Получение объявления (GET)
async def get_ad(request):
    ad_id = int(request.match_info['ad_id'])  # Достаем ID из URL
    ad = ads_db.get(ad_id)
    if not ad:
        return web.json_response({"error": "Не найдено"}, status=404)
    return web.json_response(ad, status=200)


# Удаление объявления (DELETE)
async def delete_ad(request):
    ad_id = int(request.match_info['ad_id'])
    user_id = await get_current_user(request)

    if not user_id:
        return web.json_response({"error": "Требуется авторизация"}, status=401)

    ad = ads_db.get(ad_id)
    if not ad:
        return web.json_response({"error": "Не найдено"}, status=404)

    if ad['owner_id'] != user_id:
        return web.json_response({"error": "Нет прав на удаление"}, status=403)

    del ads_db[ad_id]
    return web.json_response({"status": "deleted"}, status=200)


# --- ЗАПУСК СЕРВЕРА ---
app = web.Application()

# Прописываем маршруты (URL, метод, функция)
app.router.add_post('/register', register)
app.router.add_post('/login', login)
app.router.add_post('/advertisements', create_ad)
app.router.add_get('/advertisements/{ad_id}', get_ad)
app.router.add_delete('/advertisements/{ad_id}', delete_ad)

if __name__ == '__main__':
    web.run_app(app, host='127.0.0.1', port=8080)
