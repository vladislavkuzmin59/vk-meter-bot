import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api import upload
import sqlite3
import datetime
import re
import requests
import os
import schedule
import time
import threading
from zoneinfo import ZoneInfo

# ============================================
# ТВОИ ДАННЫЕ
# ============================================
TOKEN = os.getenv("VK_TOKEN", "vk1.a.pCHFwhkc42ELETpehxP2TqpXIJG2u2_OM448fyk-AuaDii7l2Ojp8geusVhXqw2d9YyYtRTqJoV0GtmIlgZQbhGm00vAsSokZlHu4xjQGC6rrWYwLFbhu6Z0dluFyLwcvsrFFWlUPdayo8WIOLu2Si5eSYYUOT96HP0gWe18T6tCfZS8cCt-JQo7UFhnwVHSqeM2bj1mCPtDLNLEnxm19A")
GROUP_ID = 234254762

ADMIN_IDS = [
    241341304,
    740369281,
]

# ============================================
# ПУТЬ К БАЗЕ (как было на BotHost)
# ============================================
DB_PATH = os.getenv('DB_PATH', 'users.db')

def get_db_connection():
    return sqlite3.connect(DB_PATH)

# ============================================
# РЕЖИМ ТЕСТИРОВАНИЯ ДАТ
# ============================================
TEST_DAY = 0
reminder_sent_vodokanal = False
reminder_sent_main = False

def get_current_day():
    if TEST_DAY > 0:
        return TEST_DAY
    return datetime.datetime.now().day

def get_current_month():
    return datetime.datetime.now().strftime("%Y-%m")

def reset_to_real_date():
    global TEST_DAY
    TEST_DAY = 0
    print("📅 Реальный режим восстановлен")

def reset_meter_status_for_test(group_type=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if group_type == 'vodokanal':
        cursor.execute("""
            UPDATE users SET 
                meter_photo_sent_vodokanal = 0,
                can_edit_vodokanal = 0,
                meter_photo_month_vodokanal = '',
                meter_photos_vodokanal = ''
        """)
        print("🔄 Сброшены показания водоснабжения для тестов")
    elif group_type in ('main', 'biznes_centr'):
        cursor.execute("""
            UPDATE users SET 
                meter_photo_sent_main = 0,
                meter_photo_sent_biznes = 0,
                can_edit_main = 0,
                can_edit_biznes = 0,
                meter_photo_month_main = '',
                meter_photo_month_biznes = '',
                meter_photos_main = '',
                meter_photos_biznes = ''
        """)
        print("🔄 Сброшены основные показания для тестов")
    else:
        cursor.execute("""
            UPDATE users SET 
                meter_photo_sent_main = 0,
                meter_photo_sent_biznes = 0,
                meter_photo_sent_vodokanal = 0,
                can_edit_main = 0,
                can_edit_biznes = 0,
                can_edit_vodokanal = 0,
                meter_photo_month_main = '',
                meter_photo_month_biznes = '',
                meter_photo_month_vodokanal = '',
                meter_photos_main = '',
                meter_photos_biznes = '',
                meter_photos_vodokanal = ''
        """)
        print("🔄 Сброшены все показания для тестов")
    conn.commit()
    conn.close()

def reset_old_month_status():
    """Сбрасывает флаги отправки, если они относятся к прошлому месяцу."""
    current_month = get_current_month()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET
            meter_photo_sent_vodokanal = 0,
            can_edit_vodokanal = 0,
            meter_photos_vodokanal = ''
        WHERE meter_photo_month_vodokanal != ?
          AND meter_photo_month_vodokanal != ''
    """, (current_month,))
    vod_count = cursor.rowcount
    cursor.execute("""
        UPDATE users SET
            meter_photo_sent_main = 0,
            can_edit_main = 0,
            meter_photos_main = ''
        WHERE meter_photo_month_main != ?
          AND meter_photo_month_main != ''
    """, (current_month,))
    main_count = cursor.rowcount
    cursor.execute("""
        UPDATE users SET
            meter_photo_sent_biznes = 0,
            can_edit_biznes = 0,
            meter_photos_biznes = ''
        WHERE meter_photo_month_biznes != ?
          AND meter_photo_month_biznes != ''
    """, (current_month,))
    biz_count = cursor.rowcount
    conn.commit()
    conn.close()
    if vod_count or main_count or biz_count:
        print(f"🔄 Автосброс за прошлый месяц: вода={vod_count}, осн={main_count}, бц={biz_count}")
    return vod_count, main_count, biz_count

# ============================================
# УВЕДОМЛЕНИЕ АДМИНАМ ПРИ ЗАПУСКЕ
# ============================================
def send_startup_notification(vk_session):
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    test_mode = "ВКЛЮЧЕН" if TEST_DAY > 0 else "ВЫКЛЮЧЕН"
    test_info = f"\n⚠️ ТЕСТОВЫЙ РЕЖИМ: {test_mode}" if TEST_DAY > 0 else ""
    message = f"""🤖 *БОТ ЗАПУЩЕН!*

📅 Дата и время: {now}
📱 Группа: Группа компаний АБС
✅ Статус: Работает{test_info}

📨 Напоминания отправляются автоматически
👥 Администраторы: {len(ADMIN_IDS)} человек

💡 Для управления используйте 'меню'."""
    for admin_id in ADMIN_IDS:
        try:
            send_message(vk_session, admin_id, message)
            print(f"📨 Уведомление о запуске отправлено админу {admin_id}")
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка отправки уведомления админу {admin_id}: {e}")

# ============================================
# БАЗА ДАННЫХ
# ============================================
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vk_id INTEGER UNIQUE,
            full_name TEXT,
            organization TEXT,
            address TEXT,
            room TEXT,
            mall_name TEXT,
            registration_date TEXT,
            last_active TEXT,
            notified INTEGER DEFAULT 0,
            last_meter_reading TEXT,
            meter_photo_sent_main INTEGER DEFAULT 0,
            meter_photo_sent_biznes INTEGER DEFAULT 0,
            meter_photo_sent_vodokanal INTEGER DEFAULT 0,
            temp_photos TEXT DEFAULT "",
            meter_photo_month_main TEXT DEFAULT "",
            meter_photo_month_biznes TEXT DEFAULT "",
            meter_photo_month_vodokanal TEXT DEFAULT "",
            meter_photos_main TEXT DEFAULT "",
            meter_photos_biznes TEXT DEFAULT "",
            meter_photos_vodokanal TEXT DEFAULT "",
            reminder_received_main INTEGER DEFAULT 0,
            reminder_received_biznes INTEGER DEFAULT 0,
            reminder_received_vodokanal INTEGER DEFAULT 0,
            can_edit_main INTEGER DEFAULT 0,
            can_edit_biznes INTEGER DEFAULT 0,
            can_edit_vodokanal INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vk_id INTEGER,
            group_type TEXT,
            UNIQUE(vk_id, group_type)
        )
    ''')
    cursor.execute("PRAGMA table_info(users)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    for col_name, col_def in [
        ('can_edit_main', 'INTEGER DEFAULT 0'),
        ('can_edit_biznes', 'INTEGER DEFAULT 0'),
        ('can_edit_vodokanal', 'INTEGER DEFAULT 0'),
        ('reminder_received_main', 'INTEGER DEFAULT 0'),
        ('reminder_received_biznes', 'INTEGER DEFAULT 0'),
        ('reminder_received_vodokanal', 'INTEGER DEFAULT 0'),
    ]:
        if col_name not in column_names:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_def}')
    conn.commit()
    conn.close()

def get_user(vk_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE vk_id = ?", (vk_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY registration_date DESC")
    users = cursor.fetchall()
    conn.close()
    return users

def get_user_groups(vk_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT group_type FROM user_groups WHERE vk_id = ?", (vk_id,))
    result = cursor.fetchall()
    conn.close()
    return [row[0] for row in result] if result else []

def is_user_in_group(vk_id, group_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_groups WHERE vk_id = ? AND group_type = ?", (vk_id, group_type))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_user_to_group(vk_id, group_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO user_groups (vk_id, group_type) VALUES (?, ?)", (vk_id, group_type))
        conn.commit()
    except Exception as e:
        print(f"❌ Ошибка добавления в группу: {e}")
    conn.close()

def remove_user_from_group(vk_id, group_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_groups WHERE vk_id = ? AND group_type = ?", (vk_id, group_type))
    conn.commit()
    conn.close()

def save_user(vk_id, full_name, organization="", address="", room="", mall_name=""):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE vk_id = ?", (vk_id,))
    user = cursor.fetchone()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if user:
        cursor.execute('''
            UPDATE users SET full_name = ?, organization = ?, address = ?, room = ?, mall_name = ?, last_active = ?
            WHERE vk_id = ?
        ''', (full_name, organization, address, room, mall_name, now, vk_id))
        is_new = False
    else:
        cursor.execute('''
            INSERT INTO users (vk_id, full_name, organization, address, room, mall_name, registration_date, last_active, notified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (vk_id, full_name, organization, address, room, mall_name, now, now))
        is_new = True
    conn.commit()
    conn.close()
    return is_new

def get_user_meter_status(vk_id, group_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    if group_type == 'main':
        cursor.execute("SELECT meter_photo_sent_main, can_edit_main FROM users WHERE vk_id = ?", (vk_id,))
    elif group_type == 'biznes_centr':
        cursor.execute("SELECT meter_photo_sent_biznes, can_edit_biznes FROM users WHERE vk_id = ?", (vk_id,))
    else:
        cursor.execute("SELECT meter_photo_sent_vodokanal, can_edit_vodokanal FROM users WHERE vk_id = ?", (vk_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {'sent': result[0] == 1, 'can_edit': result[1] == 1}
    return {'sent': False, 'can_edit': False}

def save_meter_photos_for_group(vk_id, photos, month, group_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    if group_type == 'main':
        cursor.execute("""UPDATE users SET meter_photos_main = ?, meter_photo_month_main = ?,
                          meter_photo_sent_main = 1, can_edit_main = 1 WHERE vk_id = ?""", (photos, month, vk_id))
    elif group_type == 'biznes_centr':
        cursor.execute("""UPDATE users SET meter_photos_biznes = ?, meter_photo_month_biznes = ?,
                          meter_photo_sent_biznes = 1, can_edit_biznes = 1 WHERE vk_id = ?""", (photos, month, vk_id))
    else:
        cursor.execute("""UPDATE users SET meter_photos_vodokanal = ?, meter_photo_month_vodokanal = ?,
                          meter_photo_sent_vodokanal = 1, can_edit_vodokanal = 1 WHERE vk_id = ?""", (photos, month, vk_id))
    conn.commit()
    conn.close()
    print(f"💾 Сохранено фото для группы {group_type}")

def get_meter_photos_for_group(vk_id, group_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    if group_type == 'main':
        cursor.execute("SELECT meter_photos_main, meter_photo_month_main FROM users WHERE vk_id = ?", (vk_id,))
    elif group_type == 'biznes_centr':
        cursor.execute("SELECT meter_photos_biznes, meter_photo_month_biznes FROM users WHERE vk_id = ?", (vk_id,))
    else:
        cursor.execute("SELECT meter_photos_vodokanal, meter_photo_month_vodokanal FROM users WHERE vk_id = ?", (vk_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0]:
        return {'photos': result[0].split(',') if result[0] else [], 'month': result[1] or ''}
    return {'photos': [], 'month': ''}

def mark_notified(vk_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET notified = 1 WHERE vk_id = ?", (vk_id,))
    conn.commit()
    conn.close()

def check_and_disable_edit():
    today = get_current_day()
    if today > 30:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET can_edit_main = 0, can_edit_biznes = 0, can_edit_vodokanal = 0")
        conn.commit()
        conn.close()
        print("🔒 Редактирование отключено (конец месяца)")
        return True
    if today > 14:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET can_edit_vodokanal = 0 WHERE can_edit_vodokanal = 1")
        conn.commit()
        conn.close()
        print("🔒 Редактирование водоснабжения отключено (после 14 числа)")
        return True
    return False

# ============================================
# ФОТО
# ============================================
def download_photo(url, filename):
    try:
        response = requests.get(url, stream=True, timeout=30)
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type:
                print(f"⚠️ Неизвестный тип файла: {content_type}")
                return False
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) == 0:
                print("⚠️ Файл пустой (0 байт)")
                return False
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(1024):
                    if chunk:
                        f.write(chunk)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return True
            print("⚠️ Файл не сохранился или пустой")
            return False
    except requests.exceptions.Timeout:
        print("❌ Таймаут при скачивании фото")
        return False
    except Exception as e:
        print(f"❌ Ошибка скачивания фото: {e}")
        return False

def upload_photo_to_vk(vk_session, filename, retries=3):
    for attempt in range(retries):
        try:
            if not os.path.exists(filename):
                print(f"❌ Файл {filename} не найден")
                return None
            file_size = os.path.getsize(filename)
            if file_size == 0:
                print(f"❌ Файл {filename} пустой")
                return None
            if file_size > 50 * 1024 * 1024:
                print(f"❌ Файл {filename} слишком большой ({file_size/1024/1024:.1f} МБ)")
                return None
            uploader = upload.VkUpload(vk_session)
            photo = uploader.photo_messages(filename)
            if photo and len(photo) > 0:
                attachment = f"photo{photo[0]['owner_id']}_{photo[0]['id']}"
                print(f"✅ Фото загружено: {attachment}")
                return attachment
            print(f"❌ Не удалось сохранить фото (попытка {attempt+1}/{retries})")
        except Exception as e:
            print(f"❌ Ошибка загрузки фото (попытка {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(1)
    return None

def get_all_photos_from_message(vk_session, peer_id, message_id):
    try:
        response = vk_session.method('messages.getById', {'message_ids': message_id})
        if response and 'items' in response and len(response['items']) > 0:
            msg = response['items'][0]
            if 'attachments' in msg:
                return [a for a in msg['attachments'] if a['type'] == 'photo']
    except Exception as e:
        print(f"❌ Ошибка получения фото: {e}")
    return []

# ============================================
# СООБЩЕНИЯ
# ============================================
user_states = {}
admin_states = {}

def send_message(vk_session, peer_id, text, keyboard=None):
    try:
        if keyboard is None:
            user = get_user(peer_id)
            if is_admin(peer_id):
                keyboard = get_admin_menu_keyboard()
            elif user:
                keyboard = get_user_menu_keyboard(peer_id)
            else:
                keyboard = get_main_with_fill_keyboard()
        params = {'peer_id': peer_id, 'message': text, 'random_id': 0}
        if keyboard:
            params['keyboard'] = keyboard
        vk_session.method('messages.send', params)
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

# ============================================
# ПЕРИОДЫ
# ============================================
def can_send_photos_for_group(group_type):
    today = get_current_day()
    if group_type == 'vodokanal':
        return 11 <= today <= 14
    return 24 <= today <= 29

def get_send_period_text(group_type):
    return "с 11 по 14 число" if group_type == 'vodokanal' else "с 24 по 29 число"

def get_active_group(vk_id):
    groups = get_user_groups(vk_id)
    today = get_current_day()
    if 11 <= today <= 14 and 'vodokanal' in groups:
        return 'vodokanal'
    if 24 <= today <= 29:
        if 'main' in groups:
            return 'main'
        if 'biznes_centr' in groups:
            return 'biznes_centr'
    return None

# ============================================
# КЛАВИАТУРЫ
# ============================================
def get_main_menu_button():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('🏠 Меню', color=VkKeyboardColor.PRIMARY)
    return keyboard.get_keyboard()

def get_user_menu_keyboard(vk_id=None):
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('📋 Моя анкета', color=VkKeyboardColor.SECONDARY)
    if vk_id:
        active_group = get_active_group(vk_id)
        if active_group:
            status = get_user_meter_status(vk_id, active_group)
            if status['sent'] and status['can_edit']:
                keyboard.add_button('🔄 Заменить показания', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('✏️ Редактировать анкету', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('❓ Помощь', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_admin_menu_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('📊 Статистика', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('📸 Показания счетчиков', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('📋 Все пользователи', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('🚰 Водоканал', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('🔧 Тест даты', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('❓ Помощь', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_test_date_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('📅 11 число', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('📅 12 число', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('📅 14 число', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('📅 24 число', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('📅 25 число', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('📅 29 число', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('📅 1 число', color=VkKeyboardColor.SECONDARY)
    keyboard.add_button('🔴 Сброс', color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button('🔙 Назад', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_vodokanal_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('📋 Список пользователей', color=VkKeyboardColor.SECONDARY)
    keyboard.add_button('➕ Добавить пользователя', color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button('🔙 Назад', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_back_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('🔙 Назад', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_location_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('⭐ БЦ 5 звезд', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('📍 Другое место', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_org_skip_keyboard_with_back():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('Нет организации', color=VkKeyboardColor.SECONDARY)
    keyboard.add_button('🔙 Назад', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_group_selection_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('Основная', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('БЦ 5 звезд', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('Водоканал', color=VkKeyboardColor.PRIMARY)
    return keyboard.get_keyboard()

def get_edit_profile_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('✅ Оставить текущее', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('🔙 Отмена', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_main_with_fill_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('📝 Заполнить анкету', color=VkKeyboardColor.PRIMARY)
    return keyboard.get_keyboard()

# ============================================
# АДМИНЫ
# ============================================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_user_name(vk_session, user_id):
    try:
        user = vk_session.method('users.get', {'user_ids': user_id})
        if user:
            return user[0]['first_name']
    except Exception:
        pass
    return "Пользователь"

def get_user_full_name(vk_session, user_id):
    try:
        user = vk_session.method('users.get', {'user_ids': user_id})
        if user:
            return f"{user[0]['first_name']} {user[0]['last_name']}"
    except Exception:
        pass
    return "Пользователь"

def extract_vk_id_from_url(text):
    patterns = [
        r'vk\.com/id(\d+)', r'vk\.com/(\d+)', r'vk\.ru/id(\d+)', r'vk\.ru/(\d+)',
        r'https?://vk\.com/id(\d+)', r'https?://vk\.com/(\d+)',
        r'https?://vk\.ru/id(\d+)', r'https?://vk\.ru/(\d+)', r'^(\d+)$'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None

# ============================================
# ВСЕ ПОЛЬЗОВАТЕЛИ
# ============================================
def show_all_users(vk_session, peer_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY registration_date DESC")
    users = cursor.fetchall()
    conn.close()
    if not users:
        send_message(vk_session, peer_id, "📋 Нет зарегистрированных пользователей.", get_admin_menu_keyboard())
        return
    message = "📋 *ВСЕ ПОЛЬЗОВАТЕЛИ*\n" + "=" * 40 + "\n\n"
    for i, user in enumerate(users, 1):
        groups = get_user_groups(user[1])
        group_names = {'main': 'Основная', 'biznes_centr': 'БЦ 5 звезд', 'vodokanal': 'Водоканал'}
        group_list = ', '.join([group_names.get(g, g) for g in groups]) if groups else 'Не указана'
        message += f"{i}. {user[2]}\n   🔗 https://vk.com/id{user[1]}\n   📍 {user[4]}\n"
        if user[5]:
            message += f"   🚪 Каб.: {user[5]}\n"
        if user[6]:
            message += f"   🛍 ТЦ: {user[6]}\n"
        if user[3]:
            message += f"   🏢 {user[3]}\n"
        message += f"   📅 Рег.: {user[7][:10]}\n   🏷️ Группы: {group_list}\n"
        status_parts = []
        has_main_or_biznes = False
        for group in groups:
            status = get_user_meter_status(user[1], group)
            status_icon = '✅' if status['sent'] else '❌'
            if group == 'vodokanal':
                status_parts.append(f"Водоснабжение: {status_icon}")
            else:
                if not has_main_or_biznes:
                    has_main_or_biznes = True
                    status_parts.append(f"Счетчики: {status_icon}")
        if status_parts:
            message += f"   📊 {', '.join(status_parts)}\n"
        message += "\n"
    if len(message) > 4000:
        parts = []
        current_part = "📋 *ВСЕ ПОЛЬЗОВАТЕЛИ*\n" + "=" * 40 + "\n\n"
        for line in message.split('\n')[2:]:
            if len(current_part + line + '\n') > 3900:
                parts.append(current_part)
                current_part = "📋 *ПРОДОЛЖЕНИЕ*\n" + "=" * 40 + "\n\n"
            current_part += line + '\n'
        parts.append(current_part)
        for part in parts:
            send_message(vk_session, peer_id, part, get_admin_menu_keyboard())
            time.sleep(0.5)
    else:
        send_message(vk_session, peer_id, message, get_admin_menu_keyboard())

# ============================================
# ОТПРАВКА АДМИНАМ
# ============================================
def send_photo_to_admins(vk_session, user, attachments, group_type):
    group_name = 'Водоснабжение (ГВС и ХВС)' if group_type == 'vodokanal' else 'Основные счетчики'
    message = f"""📸 НОВЫЕ ПОКАЗАНИЯ СЧЕТЧИКОВ - {group_name.upper()}!

👤 Арендатор: {user[2]}
🔗 Ссылка: https://vk.com/id{user[1]}
📍 Адрес: {user[4]}"""
    if user[5]:
        message += f"\n🚪 Кабинет: {user[5]}"
    if user[6]:
        message += f"\n🛍 ТЦ: {user[6]}"
    if user[3]:
        message += f"\n🏢 Организация: {user[3]}"
    message += f"\n📅 Дата: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}\n📸 Количество фото: {len(attachments)}"
    for admin_id in ADMIN_IDS:
        try:
            vk_session.method('messages.send', {
                'peer_id': admin_id, 'message': message,
                'attachment': ','.join(attachments), 'random_id': 0
            })
            print(f"📨 Уведомление отправлено админу {admin_id} ({len(attachments)} фото)")
            time.sleep(0.3)
        except Exception as e:
            print(f"❌ Ошибка отправки админу {admin_id}: {e}")

def send_admin_notification(vk_session, user_data):
    message = f"""🆕 НОВЫЙ АРЕНДАТОР!

👤 ФИО: {user_data['full_name']}
🔗 Ссылка: https://vk.com/id{user_data['vk_id']}
📍 Адрес: {user_data['address']}"""
    if user_data['room']:
        message += f"\n🚪 Кабинет: {user_data['room']}"
    if user_data['mall_name']:
        message += f"\n🛍 ТЦ: {user_data['mall_name']}"
    if user_data['organization']:
        message += f"\n🏢 Организация: {user_data['organization']}"
    message += f"\n📅 Дата регистрации: {user_data['date']}"
    for admin_id in ADMIN_IDS:
        try:
            send_message(vk_session, admin_id, message)
            time.sleep(0.3)
        except Exception as e:
            print(f"❌ Ошибка: {e}")

# ============================================
# НАПОМИНАНИЯ
# ============================================
def send_meter_reminders(vk_session):
    print("📅 Запуск ежедневного напоминания по основным счетчикам...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.* FROM users u
        JOIN user_groups ug ON u.vk_id = ug.vk_id
        WHERE ug.group_type IN ('main', 'biznes_centr')
        GROUP BY u.vk_id
    """)
    users = cursor.fetchall()
    conn.close()
    if not users:
        print("📊 Нет пользователей для уведомления")
        return
    sent_count = 0
    current_day = get_current_day()
    for user in users:
        try:
            vk_id = user[1]
            full_name = user[2]
            user_groups = get_user_groups(vk_id)
            if not any(g in ['main', 'biznes_centr'] for g in user_groups):
                continue
            status_main = get_user_meter_status(vk_id, 'main')
            status_biznes = get_user_meter_status(vk_id, 'biznes_centr')
            if (status_main and status_main['sent']) or (status_biznes and status_biznes['sent']):
                print(f"⏭️ {full_name} уже отправил показания, пропускаем")
                continue
            message = f"""🔔 УВАЖАЕМЫЙ {full_name.upper()}!

📆 Напоминание: сегодня {current_day} число!
Пожалуйста, отправьте ФОТО с ПОКАЗАНИЯМИ СЧЕТЧИКОВ.

📸 Отправьте фото в этот диалог.
⏰ Нужно отправить ДО 29 числа.

Спасибо! 🙏"""
            send_message(vk_session, vk_id, message)
            sent_count += 1
            print(f"✅ Напоминание отправлено {full_name}")
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    print(f"📨 Отправлено {sent_count} напоминаний")

def send_vodokanal_reminders(vk_session):
    print("📅 Запуск ежедневного напоминания по счетчикам водоснабжения...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.* FROM users u
        JOIN user_groups ug ON u.vk_id = ug.vk_id
        WHERE ug.group_type = 'vodokanal'
        GROUP BY u.vk_id
    """)
    users = cursor.fetchall()
    conn.close()
    if not users:
        print("📊 Нет пользователей для уведомления по водоснабжению")
        return 0
    sent_count = 0
    current_day = get_current_day()
    for user in users:
        try:
            vk_id = user[1]
            full_name = user[2]
            if 'vodokanal' not in get_user_groups(vk_id):
                continue
            status = get_user_meter_status(vk_id, 'vodokanal')
            if status and status['sent']:
                print(f"⏭️ {full_name} уже отправил показания водоснабжения, пропускаем")
                continue
            message = f"""🔔 УВАЖАЕМЫЙ {full_name.upper()}!

📆 Напоминание: сегодня {current_day} число!
Пожалуйста, отправьте ФОТО с ПОКАЗАНИЯМИ СЧЕТЧИКОВ ВОДОСНАБЖЕНИЯ (ГВС и ХВС).

📸 Отправьте фото в этот диалог.
⏰ Нужно отправить ДО 14 числа.

Спасибо! 🙏"""
            send_message(vk_session, vk_id, message)
            sent_count += 1
            print(f"✅ Напоминание отправлено {full_name}")
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    print(f"📨 Отправлено {sent_count} напоминаний по водоснабжению")
    return sent_count

# ============================================
# СТАТИСТИКА
# ============================================
def show_statistics(vk_session, peer_id):
    users = get_all_users()
    if not users:
        send_message(vk_session, peer_id, "📊 Пока нет зарегистрированных пользователей.")
        return
    current_month = get_current_month()
    groups_data = {
        'main': {'name': 'Основная', 'icon': '🏷️', 'sent': 0, 'not_sent': []},
        'biznes_centr': {'name': 'БЦ 5 звезд', 'icon': '⭐', 'sent': 0, 'not_sent': []},
        'vodokanal': {'name': 'Водоканал', 'icon': '🚰', 'sent': 0, 'not_sent': []}
    }
    for user in users:
        for group in get_user_groups(user[1]):
            if group in groups_data:
                status = get_user_meter_status(user[1], group)
                if status['sent']:
                    groups_data[group]['sent'] += 1
                else:
                    groups_data[group]['not_sent'].append(user)
    message = f"📊 СТАТИСТИКА ПОКАЗАНИЙ ЗА {current_month}\n" + "=" * 40 + "\n\n"
    for data in groups_data.values():
        total = data['sent'] + len(data['not_sent'])
        if total > 0:
            message += f"{data['icon']} *{data['name']}:*\n   👥 Отправили: {data['sent']}\n   ❌ Не отправили: {len(data['not_sent'])}\n\n"
    has_not_sent = any(data['not_sent'] for data in groups_data.values())
    if has_not_sent:
        message += "❌ *НЕ ОТПРАВИЛИ ПОКАЗАНИЯ:*\n" + "=" * 40 + "\n\n"
        for data in groups_data.values():
            if data['not_sent']:
                message += f"{data['icon']} *{data['name']}:*\n"
                for user in data['not_sent']:
                    message += f"   🔗 https://vk.com/id{user[1]}\n"
                    if user[4]:
                        message += f"      📍 {user[4]}\n"
                    if user[5]:
                        message += f"      🚪 Каб.: {user[5]}\n"
                    if user[2]:
                        message += f"      👤 {user[2]}\n"
                message += "\n"
    if len(message) > 4000:
        parts = []
        current_part = "📊 *СТАТИСТИКА ПОКАЗАНИЙ*\n" + "=" * 40 + "\n\n"
        for line in message.split('\n')[2:]:
            if len(current_part + line + '\n') > 3900:
                parts.append(current_part)
                current_part = "📊 *ПРОДОЛЖЕНИЕ СТАТИСТИКИ*\n" + "=" * 40 + "\n\n"
            current_part += line + '\n'
        parts.append(current_part)
        for part in parts:
            send_message(vk_session, peer_id, part)
            time.sleep(0.5)
    else:
        send_message(vk_session, peer_id, message)

# ============================================
# ПОКАЗАНИЯ СЧЕТЧИКОВ (админ)
# ============================================
def show_meter_readings(vk_session, peer_id, group_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.* FROM users u
        JOIN user_groups ug ON u.vk_id = ug.vk_id
        WHERE ug.group_type = ?
        ORDER BY u.registration_date DESC
    """, (group_type,))
    users = cursor.fetchall()
    conn.close()
    if not users:
        group_names = {'main': 'Основная', 'biznes_centr': 'БЦ 5 звезд', 'vodokanal': 'Водоканал'}
        send_message(vk_session, peer_id, f"📊 В группе '{group_names.get(group_type, 'Основная')}' пока нет пользователей.")
        return
    group_names = {'main': 'Основная', 'biznes_centr': 'БЦ 5 звезд', 'vodokanal': 'Водоканал'}
    group_name = group_names.get(group_type, 'Основная')
    sent_photos = []
    for user in users:
        photos_data = get_meter_photos_for_group(user[1], group_type)
        if photos_data['photos']:
            sent_photos.append({'user': user, 'photos': photos_data['photos']})
    if not sent_photos:
        send_message(vk_session, peer_id, f"📸 В группе '{group_name}' пока нет отправленных показаний.")
        return
    for item in sent_photos:
        user = item['user']
        photos = item['photos']
        message = f"""📸 ПОКАЗАНИЯ СЧЕТЧИКОВ - {group_name.upper()}

👤 Арендатор: {user[2]}
🔗 Ссылка: https://vk.com/id{user[1]}
📍 Адрес: {user[4]}"""
        if user[5]:
            message += f"\n🚪 Кабинет: {user[5]}"
        if user[3]:
            message += f"\n🏢 Организация: {user[3]}"
        if user[6]:
            message += f"\n🛍 ТЦ: {user[6]}"
        message += f"\n📅 Дата регистрации: {user[7][:10]}\n📸 Количество фото: {len(photos)}"
        try:
            vk_session.method('messages.send', {
                'peer_id': peer_id, 'message': message,
                'attachment': ','.join(photos), 'random_id': 0
            })
            print(f"📨 Отправлены фото для {user[2]} ({len(photos)} фото)")
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    send_message(vk_session, peer_id, f"✅ Все показания для группы '{group_name}' отправлены.")

# ============================================
# ВОДОКАНАЛ
# ============================================
def show_vodokanal_users(vk_session, peer_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.* FROM users u
        JOIN user_groups ug ON u.vk_id = ug.vk_id
        WHERE ug.group_type = 'vodokanal'
        ORDER BY u.registration_date DESC
    """)
    users = cursor.fetchall()
    conn.close()
    if not users:
        send_message(vk_session, peer_id, "📋 В группе 'Водоканал' пока нет пользователей.", get_vodokanal_keyboard())
        return
    message = "📋 *ПОЛЬЗОВАТЕЛИ ВОДОКАНАЛА*\n" + "=" * 40 + "\n\n"
    for i, user in enumerate(users, 1):
        message += f"{i}. {user[2]}\n   🔗 https://vk.com/id{user[1]}\n"
        if user[4]:
            message += f"   📍 {user[4]}\n"
        if user[5]:
            message += f"   🚪 Каб.: {user[5]}\n"
        if user[3]:
            message += f"   🏢 {user[3]}\n"
        if user[6]:
            message += f"   🛍 ТЦ: {user[6]}\n"
        message += f"   📅 Рег.: {user[7][:10]}\n\n"
    send_message(vk_session, peer_id, message, get_vodokanal_keyboard())

def start_add_user_to_vodokanal(vk_session, peer_id):
    admin_states[peer_id] = {'step': 'waiting_vk_link', 'menu': 'vodokanal'}
    send_message(vk_session, peer_id,
        "➕ *ДОБАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ В ВОДОКАНАЛ*\n\n"
        "Отправьте ссылку на профиль пользователя ВК.\n"
        "📌 *Пример:* https://vk.com/id123456789\n\n"
        "Пользователь будет добавлен в группу 'Водоканал'.",
        get_back_keyboard())

# ============================================
# ТЕСТОВЫЕ КОМАНДЫ
# ============================================
def show_test_menu(vk_session, peer_id):
    current_day = get_current_day()
    real_day = datetime.datetime.now().day
    test_mode = "ВКЛЮЧЕН" if TEST_DAY > 0 else "ВЫКЛЮЧЕН"
    message = f"""🔧 *ТЕСТОВЫЙ РЕЖИМ*

📅 Текущая тестовая дата: {current_day} число
📅 Реальная дата: {real_day} число
📌 Режим: {test_mode}

*При установке тестовой даты:*
🔄 Сбрасываются только показания для активного периода приема
📨 Напоминания отправляются мгновенно

*Периоды приема показаний:*
• Счетчики водоснабжения (ГВС и ХВС): с 11 по 14 число
• Остальные счетчики: с 24 по 29 число

Выберите дату для тестирования:"""
    send_message(vk_session, peer_id, message, get_test_date_keyboard())

# ============================================
# РЕДАКТИРОВАНИЕ АНКЕТЫ
# ============================================
def start_edit_profile(vk_session, peer_id, from_id):
    user = get_user(from_id)
    if not user:
        send_message(vk_session, peer_id, "❌ Вы еще не заполнили анкету.", get_main_with_fill_keyboard())
        return
    current_data = {
        'full_name': user[2], 'organization': user[3] or '',
        'address': user[4], 'room': user[5] or '', 'mall_name': user[6] or ''
    }
    groups = get_user_groups(from_id)
    is_biznes = 'biznes_centr' in groups
    location_type = 'biznes_centr' if is_biznes else 'main'
    user_states[from_id] = {
        'step': 'edit_address',
        'data': {
            'full_name': current_data['full_name'], 'organization': current_data['organization'],
            'address': current_data['address'], 'room': current_data['room'],
            'mall_name': current_data['mall_name'], 'location_type': location_type,
            'is_biznes': is_biznes
        },
        'is_edit': True
    }
    send_message(vk_session, peer_id,
        f"✏️ *РЕДАКТИРОВАНИЕ АНКЕТЫ*\n\n"
        f"📍 Текущий адрес: {current_data['address']}\n\n"
        f"Введите НОВЫЙ АДРЕС или нажмите 'Оставить текущее':\n"
        f"📌 *Пример:* Ул. 20-летия Победы 173В",
        get_edit_profile_keyboard())

# ============================================
# РАСПИСАНИЕ (окно 9:00–17:59 по Пермскому краю)
# ============================================
def setup_schedule(vk_session):
    def check_and_send():
        global reminder_sent_vodokanal, reminder_sent_main

        # Автосброс статусов за прошлый месяц
        # ⚠️ Если в твоём файле НЕТ функции reset_old_month_status — удали эту строку
        reset_old_month_status()

        # Окно отправки: 9:00–17:59 строго по Пермскому краю (UTC+5)
        now_perm = datetime.datetime.now(ZoneInfo("Asia/Yekaterinburg"))
        if now_perm.hour < 9 or now_perm.hour >= 18:
            return

        today = get_current_day()

        if 11 <= today <= 14 and not reminder_sent_vodokanal:
            print(f"📅 Сегодня {today} число! Отправляю напоминание по водоснабжению...")
            send_vodokanal_reminders(vk_session)
            reminder_sent_vodokanal = True
        elif today < 11 or today > 14:
            reminder_sent_vodokanal = False

        if 24 <= today <= 29 and not reminder_sent_main:
            print(f"📅 Сегодня {today} число! Отправляю напоминание по основным счетчикам...")
            send_meter_reminders(vk_session)
            reminder_sent_main = True
        elif today < 24 or today > 29:
            reminder_sent_main = False

    schedule.every(1).hours.do(check_and_send)
    print("⏰ Расписание настроено (проверка каждый час)")
    print("   • Отправка только с 9:00 до 17:59 по Пермскому краю")
    print("   • Счетчики водоснабжения: с 11 по 14 число")
    print("   • Остальные счетчики: с 24 по 29 число")

# ============================================
# ЗАПУСК
# ============================================
print("=" * 60)
print("🤖 БОТ ДЛЯ ПОКАЗАНИЙ СЧЕТЧИКОВ ЗАПУЩЕН!")
print("📱 Группа: Группа компаний АБС")
print(f"👥 Администраторы:")
for admin_id in ADMIN_IDS:
    print(f"   • https://vk.com/id{admin_id}")
print("📅 Периоды приема показаний:")
print("   • Счетчики водоснабжения (ГВС и ХВС): с 11 по 14 число")
print("   • Остальные счетчики: с 24 по 29 число")
print("📨 Напоминания отправляются ежедневно в период приема")
print("⏰ Окно отправки: 9:00–17:59 по Пермскому краю")
if TEST_DAY > 0:
    print(f"⚠️ ТЕСТОВЫЙ РЕЖИМ: сегодня = {TEST_DAY} число")
print("=" * 60)

init_db()
reset_old_month_status()  # ⚠️ Если функции нет — удали эту строку

vk_session_global = None

def reminder_main_job():
    global vk_session_global
    if vk_session_global:
        send_meter_reminders(vk_session_global)

def reminder_vodokanal_job():
    global vk_session_global
    if vk_session_global:
        send_vodokanal_reminders(vk_session_global)

try:
    vk_session_global = vk_api.VkApi(token=TOKEN, api_version='5.131')
    longpoll = VkBotLongPoll(vk_session_global, GROUP_ID)
    print("✅ Бот готов к работе!")
    print("=" * 60)
    print()
    time.sleep(2)
    send_startup_notification(vk_session_global)

    def run_schedule():
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                print(f"❌ Ошибка в планировщике: {e}")
            time.sleep(60)

    schedule_thread = threading.Thread(target=run_schedule, daemon=True)
    schedule_thread.start()
    setup_schedule(vk_session_global)

    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            check_and_disable_edit()
            msg = event.obj.message
            text = msg['text'].lower().strip() if 'text' in msg else ""
            peer_id = msg['peer_id']
            from_id = msg['from_id']
            message_id = msg.get('id')
            if from_id < 0 and abs(from_id) == GROUP_ID:
                continue
            print(f"📩 {text} (от {from_id})")

            # ГЛАВНАЯ КНОПКА "МЕНЮ"
            if text == "🏠 меню":
                if peer_id in admin_states:
                    del admin_states[peer_id]
                if peer_id in user_states:
                    del user_states[peer_id]
                user = get_user(from_id)
                user_name = get_user_name(vk_session_global, from_id)
                if is_admin(from_id):
                    admin_menu_text = f"""👋 ЗДРАВСТВУЙТЕ, {user_name.upper()}!

🔑 *АДМИН-ПАНЕЛЬ*

📊 *Управление пользователями:*
• 'статистика' - статистика по показаниям за месяц
• 'показания счетчиков' - просмотр фото показаний по группам
• 'все пользователи' - полная информация о всех пользователях

🚰 *Водоканал:*
• Управление отдельной группой пользователей

🔧 *Тестирование:*
• 'тест дата' - открыть меню тестирования дат

👥 Администраторы: {len(ADMIN_IDS)} человек"""
                    send_message(vk_session_global, peer_id, admin_menu_text)
                    continue
                if user:
                    send_message(vk_session_global, peer_id, f"👋 С возвращением, {user_name}!\n\n📋 *Главное меню*\n\nВыберите действие:")
                    continue
                send_message(vk_session_global, peer_id,
                    f"👋 Добро пожаловать, {user_name}!\n\nДля начала заполните анкету, нажав кнопку ниже.",
                    get_main_with_fill_keyboard())
                continue

            # ТЕСТ ДАТЫ - КНОПКИ
            if text in ["📅 1 число", "📅 11 число", "📅 12 число", "📅 14 число",
                        "📅 24 число", "📅 25 число", "📅 29 число"] and is_admin(from_id):
                global TEST_DAY
                day_map = {
                    "📅 1 число": 1, "📅 11 число": 11, "📅 12 число": 12,
                    "📅 14 число": 14, "📅 24 число": 24, "📅 25 число": 25, "📅 29 число": 29
                }
                new_day = day_map.get(text)
                if new_day:
                    TEST_DAY = new_day
                    if 11 <= new_day <= 14:
                        reset_meter_status_for_test('vodokanal')
                    elif 24 <= new_day <= 29:
                        reset_meter_status_for_test('main')
                    reminder_sent_vodokanal = False
                    reminder_sent_main = False
                    today = get_current_day()
                    message = f"✅ Тестовая дата установлена: {today} число\n"
                    if 11 <= today <= 14:
                        message += "🔄 Сброшены показания водоснабжения\n\n📨 Отправляю напоминание по счетчикам водоснабжения...\n"
                        reminder_vodokanal_job()
                        reminder_sent_vodokanal = True
                    elif 24 <= today <= 29:
                        message += "🔄 Сброшены основные показания\n\n📨 Отправляю напоминание по остальным счетчикам...\n"
                        reminder_main_job()
                        reminder_sent_main = True
                    else:
                        message += "📅 Сегодня не период приема показаний.\n   • Счетчики водоснабжения: с 11 по 14 число\n   • Остальные счетчики: с 24 по 29 число"
                    send_message(vk_session_global, peer_id, message)
                    continue

            # ТЕСТ ДАТЫ - СБРОС
            if text == "🔴 сброс" and is_admin(from_id):
                reset_to_real_date()
                send_message(vk_session_global, peer_id,
                    f"✅ Реальный режим восстановлен.\n📅 Сегодня {datetime.datetime.now().day} число.")
                continue

            # НАЗАД (админ)
            if text == "🔙 назад" and is_admin(from_id):
                if peer_id in admin_states:
                    del admin_states[peer_id]
                user_name = get_user_name(vk_session_global, from_id)
                admin_menu_text = f"""👋 ЗДРАВСТВУЙТЕ, {user_name.upper()}!

🔑 *АДМИН-ПАНЕЛЬ*

📊 *Управление пользователями:*
• 'статистика' - статистика по показаниям за месяц
• 'показания счетчиков' - просмотр фото показаний по группам
• 'все пользователи' - полная информация о всех пользователях

🚰 *Водоканал:*
• Управление отдельной группой пользователей

🔧 *Тестирование:*
• 'тест дата' - открыть меню тестирования дат

👥 Администраторы: {len(ADMIN_IDS)} человек"""
                send_message(vk_session_global, peer_id, admin_menu_text)
                continue

            # ТЕСТ ДАТЫ (команда)
            if text == "🔧 тест даты" and is_admin(from_id):
                show_test_menu(vk_session_global, peer_id)
                continue

            if text.startswith("тест") and is_admin(from_id):
                parts = text.split()
                if len(parts) >= 3 and parts[1] == "дата":
                    try:
                        new_day = int(parts[2])
                        if 1 <= new_day <= 31:
                            TEST_DAY = new_day
                            if 11 <= new_day <= 14:
                                reset_meter_status_for_test('vodokanal')
                            elif 24 <= new_day <= 29:
                                reset_meter_status_for_test('main')
                            reminder_sent_vodokanal = False
                            reminder_sent_main = False
                            today = get_current_day()
                            message = f"✅ Тестовая дата установлена: {today} число\n"
                            if 11 <= today <= 14:
                                message += "🔄 Сброшены показания водоснабжения\n\n📨 Отправляю напоминание по счетчикам водоснабжения...\n"
                                reminder_vodokanal_job()
                                reminder_sent_vodokanal = True
                            elif 24 <= today <= 29:
                                message += "🔄 Сброшены основные показания\n\n📨 Отправляю напоминание по остальным счетчикам...\n"
                                reminder_main_job()
                                reminder_sent_main = True
                            else:
                                message += "📅 Сегодня не период приема показаний.\n   • Счетчики водоснабжения: с 11 по 14 число\n   • Остальные счетчики: с 24 по 29 число"
                            send_message(vk_session_global, peer_id, message)
                        else:
                            send_message(vk_session_global, peer_id, "❌ Введите число от 1 до 31")
                    except ValueError:
                        send_message(vk_session_global, peer_id, "❌ Введите число. Пример: 'тест дата 11'")
                elif text == "тест сброс":
                    reset_to_real_date()
                    send_message(vk_session_global, peer_id, f"✅ Реальный режим восстановлен. Сегодня {datetime.datetime.now().day} число.")
                else:
                    show_test_menu(vk_session_global, peer_id)
                continue

            # ВСЕ ПОЛЬЗОВАТЕЛИ
            if text == "📋 все пользователи" and is_admin(from_id):
                show_all_users(vk_session_global, peer_id)
                continue

            # ОБРАБОТКА ФОТО
            if 'attachments' in msg:
                current_photos = [attach for attach in msg['attachments'] if attach['type'] == 'photo']
                if len(current_photos) <= 1 and message_id:
                    all_photos = get_all_photos_from_message(vk_session_global, peer_id, message_id)
                    if len(all_photos) > len(current_photos):
                        current_photos = all_photos
                        print(f"📸 Получено {len(current_photos)} фото через API")
                if current_photos:
                    if is_admin(from_id):
                        group_type = None
                        is_edit = False
                        if peer_id in admin_states and admin_states[peer_id].get('step') == 'edit_photos':
                            group_type = admin_states[peer_id].get('group_type')
                            is_edit = True
                        if not group_type:
                            today = get_current_day()
                            if 11 <= today <= 14:
                                group_type = 'vodokanal'
                            elif 24 <= today <= 29:
                                group_type = 'main'
                            else:
                                send_message(vk_session_global, peer_id, "❌ Сейчас не период приема показаний.")
                                continue
                        attachments = []
                        success_count = 0
                        failed_count = 0
                        for i, photo_data in enumerate(current_photos):
                            try:
                                photo = photo_data['photo']
                                photo_url = max(photo['sizes'], key=lambda x: x['width'] * x['height'])['url']
                                filename = f"meter_{from_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{i+1}.jpg"
                                print(f"📸 Обработка фото {i+1}/{len(current_photos)}")
                                if download_photo(photo_url, filename):
                                    attachment = upload_photo_to_vk(vk_session_global, filename)
                                    if attachment:
                                        attachments.append(attachment)
                                        success_count += 1
                                        print(f"✅ Фото {i+1} загружено")
                                    else:
                                        failed_count += 1
                                else:
                                    failed_count += 1
                                if os.path.exists(filename):
                                    os.remove(filename)
                            except Exception as e:
                                failed_count += 1
                                print(f"❌ Ошибка обработки фото {i+1}: {e}")
                        if attachments:
                            group_name = 'Водоканал' if group_type == 'vodokanal' else 'Основная'
                            send_message(vk_session_global, peer_id,
                                f"✅ *Фото для группы '{group_name}' обработаны!*\n\n"
                                f"📸 Отправлено фото: {success_count}{f' ({failed_count} не загружено)' if failed_count else ''}")
                        else:
                            send_message(vk_session_global, peer_id, "❌ Не удалось обработать фото.")
                        continue

                    user = get_user(from_id)
                    if not user:
                        send_message(vk_session_global, peer_id, "❌ Сначала заполните анкету.", get_main_with_fill_keyboard())
                        continue
                    group_type = None
                    is_edit = False
                    if peer_id in admin_states and admin_states[peer_id].get('step') == 'edit_photos':
                        group_type = admin_states[peer_id].get('group_type')
                        is_edit = True
                    if not group_type:
                        today = get_current_day()
                        user_groups = get_user_groups(from_id)
                        if not user_groups:
                            send_message(vk_session_global, peer_id, "❌ Вы не состоите ни в одной группе.")
                            continue
                        if 11 <= today <= 14:
                            if 'vodokanal' in user_groups:
                                group_type = 'vodokanal'
                            else:
                                send_message(vk_session_global, peer_id,
                                    "❌ *Сейчас период приема показаний водоснабжения (с 11 по 14 число).*\n\n"
                                    "💡 Но вы не состоите в группе 'Водоканал'.\nОбратитесь к администратору для добавления.")
                                continue
                        elif 24 <= today <= 29:
                            if 'main' in user_groups:
                                group_type = 'main'
                            elif 'biznes_centr' in user_groups:
                                group_type = 'biznes_centr'
                            else:
                                send_message(vk_session_global, peer_id,
                                    "❌ *Сейчас период приема показаний для основных счетчиков (с 24 по 29 число).*\n\n"
                                    "💡 Но вы не состоите в группах 'Основная' или 'БЦ 5 звезд'.\nОбратитесь к администратору для добавления.")
                                continue
                        else:
                            send_message(vk_session_global, peer_id,
                                "❌ *Сейчас не время отправки показаний.*\n\n"
                                "💡 Дождитесь напоминания от бота.\nБот пришлет уведомление, когда нужно будет отправить показания.")
                            continue
                    if not group_type:
                        send_message(vk_session_global, peer_id, "❌ Не удалось определить группу для отправки.")
                        continue
                    if not is_edit:
                        status = get_user_meter_status(from_id, group_type)
                        if status['sent']:
                            group_name = 'Основная' if group_type != 'vodokanal' else 'Водоканал'
                            send_message(vk_session_global, peer_id,
                                f"❌ *Вы уже отправили показания для группы '{group_name}'.*\n\n"
                                f"🔄 Если хотите заменить их, нажмите кнопку 'Заменить показания' в меню.")
                            continue
                    attachments = []
                    success_count = 0
                    failed_count = 0
                    for i, photo_data in enumerate(current_photos):
                        try:
                            photo = photo_data['photo']
                            photo_url = max(photo['sizes'], key=lambda x: x['width'] * x['height'])['url']
                            filename = f"meter_{from_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{i+1}.jpg"
                            print(f"📸 Обработка фото {i+1}/{len(current_photos)}")
                            if download_photo(photo_url, filename):
                                attachment = upload_photo_to_vk(vk_session_global, filename)
                                if attachment:
                                    attachments.append(attachment)
                                    success_count += 1
                                    print(f"✅ Фото {i+1} загружено")
                                else:
                                    failed_count += 1
                                    print(f"⚠️ Не удалось загрузить фото {i+1}")
                            else:
                                failed_count += 1
                                print(f"⚠️ Не удалось скачать фото {i+1}")
                            if os.path.exists(filename):
                                os.remove(filename)
                        except Exception as e:
                            failed_count += 1
                            print(f"❌ Ошибка обработки фото {i+1}: {e}")
                    if attachments:
                        save_meter_photos_for_group(from_id, ','.join(attachments), get_current_month(), group_type)
                        send_photo_to_admins(vk_session_global, user, attachments, group_type)
                        group_name = 'Водоканал' if group_type == 'vodokanal' else 'Основная'
                        if is_edit:
                            send_message(vk_session_global, peer_id,
                                f"✅ *Показания для группы '{group_name}' обновлены!*\n\n"
                                f"📸 Отправлено фото: {success_count}{f' ({failed_count} не загружено)' if failed_count else ''}")
                        else:
                            send_message(vk_session_global, peer_id,
                                f"✅ *Показания для группы '{group_name}' отправлены!*\n\n"
                                f"📸 Отправлено фото: {success_count}{f' ({failed_count} не загружено)' if failed_count else ''}\n\n"
                                f"📸 Если вы отправили не то фото, нажмите кнопку 'Заменить показания' в меню.\n\n"
                                f"💡 Следующее напоминание придет в следующем периоде приема показаний.")
                        if peer_id in admin_states:
                            del admin_states[peer_id]
                    else:
                        send_message(vk_session_global, peer_id,
                            "❌ Не удалось обработать фото. Попробуйте другие фото.\n\n"
                            "💡 Дождитесь напоминания от бота в период приема показаний.")
                    continue

            if not text and 'attachments' not in msg:
                continue

            # АДМИН-СТЕЙТЫ
            if peer_id in admin_states:
                state = admin_states[peer_id]
                if text == "🔙 назад" and state.get('step') == 'edit_photos':
                    del admin_states[peer_id]
                    send_message(vk_session_global, peer_id, "❌ Замена показаний отменена.")
                    continue
                if state.get('step') == 'waiting_vk_link':
                    vk_id = extract_vk_id_from_url(text)
                    if not vk_id:
                        send_message(vk_session_global, peer_id,
                            "❌ Не удалось определить VK ID.\n📌 *Пример:* https://vk.com/id123456789",
                            get_back_keyboard())
                        continue
                    user = get_user(vk_id)
                    if user:
                        add_user_to_group(vk_id, 'vodokanal')
                        send_message(vk_session_global, peer_id,
                            f"✅ Пользователь {user[2]} добавлен в группу 'Водоканал'!",
                            get_vodokanal_keyboard())
                        del admin_states[peer_id]
                    else:
                        send_message(vk_session_global, peer_id,
                            "❌ Пользователь не найден. Сначала заполните анкету.",
                            get_vodokanal_keyboard())
                        del admin_states[peer_id]
                    continue
                if state.get('step') == 'select_group_for_edit':
                    group_map = {'основная': 'main', 'бц 5 звезд': 'biznes_centr', 'водоканал': 'vodokanal'}
                    group_type = group_map.get(text)
                    if group_type and is_user_in_group(from_id, group_type):
                        admin_states[peer_id] = {'step': 'edit_photos', 'group_type': group_type}
                        send_message(vk_session_global, peer_id,
                            f"🔄 *ЗАМЕНА ПОКАЗАНИЙ - {text.upper()}*\n\nОтправьте НОВЫЕ ФОТО.\nСтарые будут заменены.",
                            get_back_keyboard())
                    else:
                        send_message(vk_session_global, peer_id, "❌ Выберите корректную группу.")
                    continue

            # МОЯ АНКЕТА
            if text == "📋 моя анкета":
                user = get_user(from_id)
                if user:
                    answer = f"""📋 ВАША АНКЕТА:

👤 ФИО: {user[2]}
🔗 Ссылка: https://vk.com/id{user[1]}
📍 Адрес: {user[4]}"""
                    if user[5]:
                        answer += f"\n🚪 Кабинет: {user[5]}"
                    if user[6]:
                        answer += f"\n🛍 ТЦ: {user[6]}"
                    if user[3]:
                        answer += f"\n🏢 Организация: {user[3]}"
                    answer += f"\n📅 Регистрация: {user[7][:10]}\n\n📸 *Как отправить показания:*\nДождитесь напоминания от бота и отправьте ФОТО счетчиков в этот диалог."
                    if is_admin(from_id):
                        groups = get_user_groups(from_id)
                        group_names = {'main': 'Основная', 'biznes_centr': 'БЦ 5 звезд', 'vodokanal': 'Водоканал'}
                        group_list = ', '.join([group_names.get(g, g) for g in groups]) if groups else 'Не указана'
                        answer += f"\n🏷️ Группы: {group_list}"
                        if groups:
                            answer += "\n\n📸 *Статус показаний:*"
                            for group in groups:
                                status = get_user_meter_status(from_id, group)
                                answer += f"\n   • {group_names.get(group, group)}: {'✅ Отправлены' if status['sent'] else '❌ Не отправлены'}"
                    send_message(vk_session_global, peer_id, answer)
                else:
                    send_message(vk_session_global, peer_id, "❌ Вы еще не заполнили анкету!", get_main_with_fill_keyboard())
                continue

            # ЗАМЕНИТЬ ПОКАЗАНИЯ
            if text == "🔄 заменить показания":
                user = get_user(from_id)
                if not user:
                    send_message(vk_session_global, peer_id, "❌ Сначала заполните анкету.", get_main_with_fill_keyboard())
                    continue
                active_group = get_active_group(from_id)
                if not active_group:
                    send_message(vk_session_global, peer_id,
                        "❌ *Сейчас не период приема показаний.*\n\n💡 Замена показаний возможна только в период приема.")
                    continue
                status = get_user_meter_status(from_id, active_group)
                if not status['sent'] or not status['can_edit']:
                    send_message(vk_session_global, peer_id, "❌ Нет показаний для замены в текущий период.")
                    continue
                group_names = {'main': 'Основная', 'biznes_centr': 'БЦ 5 звезд', 'vodokanal': 'Водоканал'}
                admin_states[peer_id] = {'step': 'edit_photos', 'group_type': active_group}
                send_message(vk_session_global, peer_id,
                    f"🔄 *ЗАМЕНА ПОКАЗАНИЙ - {group_names.get(active_group, active_group).upper()}*\n\n"
                    f"Отправьте НОВЫЕ ФОТО.\nСтарые будут заменены.",
                    get_back_keyboard())
                continue

            # РЕДАКТИРОВАТЬ АНКЕТУ
            if text == "✏️ редактировать анкету":
                user = get_user(from_id)
                if not user:
                    send_message(vk_session_global, peer_id, "❌ Вы еще не заполнили анкету.", get_main_with_fill_keyboard())
                    continue
                if from_id in user_states and user_states[from_id].get('is_edit', False):
                    send_message(vk_session_global, peer_id, "⚠️ Вы уже редактируете анкету.", get_edit_profile_keyboard())
                    continue
                start_edit_profile(vk_session_global, peer_id, from_id)
                continue

            # СТАТИСТИКА
            if text in ["статистика", "📊 статистика"] and is_admin(from_id):
                show_statistics(vk_session_global, peer_id)
                continue

            # ПОКАЗАНИЯ СЧЕТЧИКОВ
            if text == "📸 показания счетчиков" and is_admin(from_id):
                send_message(vk_session_global, peer_id, "📊 Выберите группу для просмотра:", get_group_selection_keyboard())
                continue

            if text in ["основная", "бц 5 звезд", "водоканал"] and is_admin(from_id):
                group_map = {'основная': 'main', 'бц 5 звезд': 'biznes_centr', 'водоканал': 'vodokanal'}
                show_meter_readings(vk_session_global, peer_id, group_map.get(text))
                continue

            # ВОДОКАНАЛ
            if text == "🚰 водоканал" and is_admin(from_id):
                if peer_id in admin_states:
                    del admin_states[peer_id]
                admin_states[peer_id] = {'menu': 'vodokanal'}
                send_message(vk_session_global, peer_id, "🚰 *УПРАВЛЕНИЕ ГРУППОЙ ВОДОКАНАЛ*\n\nВыберите действие:", get_vodokanal_keyboard())
                continue

            if text == "📋 список пользователей" and is_admin(from_id):
                show_vodokanal_users(vk_session_global, peer_id)
                continue

            if text == "➕ добавить пользователя" and is_admin(from_id):
                start_add_user_to_vodokanal(vk_session_global, peer_id)
                continue

            # ПОМОЩЬ
            if text == "❓ помощь":
                user = get_user(from_id)
                if is_admin(from_id):
                    admin_name = get_user_name(vk_session_global, from_id)
                    help_text = f"""🤖 *АДМИН-ПАНЕЛЬ* {admin_name}

📝 *Основные команды:*
• 'меню' - показать админ-панель

📊 *Управление пользователями:*
• 'статистика' - статистика по показаниям за месяц
• 'показания счетчиков' - просмотр фото показаний по группам
• 'все пользователи' - полная информация о всех пользователях
• 'водоканал' - управление группой Водоканал

🔧 *Тестирование:*
• 'тест дата [число]' - установить тестовую дату
• 'тест сброс' - вернуть реальную дату

👥 *Администраторы:* {len(ADMIN_IDS)} человек"""
                    send_message(vk_session_global, peer_id, help_text)
                else:
                    if user:
                        help_text = f"""🤖 *СПИСОК КОМАНД БОТА*

📝 *Доступные действия:*
• 'меню' - показать главное меню
• 'моя анкета' - посмотреть свои данные
• 'редактировать анкету' - изменить данные

📸 *Отправка показаний:*
• Дождитесь напоминания от бота и отправьте ФОТО счетчиков
• После отправки появится кнопка «🔄 Заменить показания»

💡 *Важно:*
• Дождитесь напоминания от бота
• Бот сам пришлет уведомление, когда нужно отправить показания

👤 *Администратор:* https://vk.com/id{ADMIN_IDS[0]}"""
                        send_message(vk_session_global, peer_id, help_text)
                    else:
                        help_text = f"""🤖 *СПИСОК КОМАНД БОТА*

📝 *Для начала работы:*
• Нажмите 'меню' и выберите 'Заполнить анкету'

👤 *Администратор:* https://vk.com/id{ADMIN_IDS[0]}"""
                        send_message(vk_session_global, peer_id, help_text, get_main_with_fill_keyboard())
                continue

            # НАЧАТЬ
            if text in ["начать", "start", "привет"]:
                user = get_user(from_id)
                user_name = get_user_name(vk_session_global, from_id)
                if user:
                    send_message(vk_session_global, peer_id, f"👋 С возвращением, {user_name}!\n\n📋 Главное меню")
                else:
                    send_message(vk_session_global, peer_id,
                        f"👋 Добро пожаловать, {user_name}!\n\nДля начала заполните анкету, нажав кнопку ниже.",
                        get_main_with_fill_keyboard())
                continue

            # ЗАПОЛНИТЬ АНКЕТУ
            if text == "📝 заполнить анкету":
                user = get_user(from_id)
                if user:
                    send_message(vk_session_global, peer_id, "✅ Вы уже заполнили анкету!")
                    continue
                user_name = get_user_name(vk_session_global, from_id)
                user_states[from_id] = {
                    'step': 'waiting_location',
                    'data': {'full_name': get_user_full_name(vk_session_global, from_id), 'organization': '', 'mall_name': ''}
                }
                send_message(vk_session_global, peer_id,
                    f"👋 Приветствую, {user_name}!\n\n📝 Заполните анкету.\n📍 Выберите место:",
                    get_location_keyboard())
                continue

            # ОБРАБОТКА АНКЕТЫ
            if from_id in user_states:
                state = user_states[from_id]
                step = state['step']
                data = state['data']
                is_edit = state.get('is_edit', False)
                if text == "✅ оставить текущее" and is_edit:
                    if step == 'edit_address':
                        user_states[from_id]['step'] = 'edit_room'
                        if data.get('is_biznes', False):
                            current_room = data.get('room', '')
                            if current_room:
                                send_message(vk_session_global, peer_id,
                                    f"✅ Адрес сохранен: {data['address']}\n\n🚪 Текущий кабинет: {current_room}\n\nВведите НОВЫЙ КАБИНЕТ или нажмите 'Оставить текущее':",
                                    get_edit_profile_keyboard())
                            else:
                                send_message(vk_session_global, peer_id,
                                    f"✅ Адрес сохранен: {data['address']}\n\n🚪 Введите КАБИНЕТ (или 'Оставить текущее'):",
                                    get_edit_profile_keyboard())
                        else:
                            user_states[from_id]['step'] = 'edit_mall'
                            current_mall = data.get('mall_name', '')
                            if current_mall:
                                send_message(vk_session_global, peer_id,
                                    f"✅ Адрес сохранен: {data['address']}\n\n🛍 Текущий ТЦ: {current_mall}\n\nВведите НОВЫЙ ТЦ или нажмите 'Оставить текущее':",
                                    get_edit_profile_keyboard())
                            else:
                                send_message(vk_session_global, peer_id,
                                    f"✅ Адрес сохранен: {data['address']}\n\n🛍 Введите ТЦ (или 'Оставить текущее'):",
                                    get_edit_profile_keyboard())
                        continue
                    elif step == 'edit_room':
                        user_states[from_id]['step'] = 'edit_mall'
                        current_mall = data.get('mall_name', '')
                        if current_mall:
                            send_message(vk_session_global, peer_id,
                                f"✅ Кабинет сохранен: {data['room'] if data.get('room') else 'Не указан'}\n\n🛍 Текущий ТЦ: {current_mall}\n\nВведите НОВЫЙ ТЦ или нажмите 'Оставить текущее':",
                                get_edit_profile_keyboard())
                        else:
                            send_message(vk_session_global, peer_id,
                                f"✅ Кабинет сохранен: {data['room'] if data.get('room') else 'Не указан'}\n\n🛍 Введите ТЦ (или 'Оставить текущее'):",
                                get_edit_profile_keyboard())
                        continue
                    elif step == 'edit_mall':
                        user_states[from_id]['step'] = 'edit_org'
                        current_org = data.get('organization', '')
                        if current_org:
                            send_message(vk_session_global, peer_id,
                                f"✅ ТЦ сохранен: {data['mall_name'] if data.get('mall_name') else 'Не указан'}\n\n🏢 Текущая организация: {current_org}\n\nВведите НОВУЮ ОРГАНИЗАЦИЮ или нажмите 'Оставить текущее':",
                                get_edit_profile_keyboard())
                        else:
                            send_message(vk_session_global, peer_id,
                                f"✅ ТЦ сохранен: {data['mall_name'] if data.get('mall_name') else 'Не указан'}\n\n🏢 Введите ОРГАНИЗАЦИЮ (или 'Оставить текущее'):",
                                get_edit_profile_keyboard())
                        continue
                    elif step == 'edit_org':
                        save_user(from_id, data['full_name'], data['organization'], data['address'], data.get('room', ''), data.get('mall_name', ''))
                        if data.get('location_type') == 'biznes_centr':
                            add_user_to_group(from_id, 'biznes_centr')
                            remove_user_from_group(from_id, 'main')
                        else:
                            add_user_to_group(from_id, 'main')
                            remove_user_from_group(from_id, 'biznes_centr')
                        send_message(vk_session_global, peer_id, "✅ Анкета обновлена!")
                        del user_states[from_id]
                        continue
                if text == "🔙 отмена" and is_edit:
                    del user_states[from_id]
                    send_message(vk_session_global, peer_id, "❌ Редактирование отменено.")
                    continue
                if is_edit:
                    if step == 'edit_address':
                        data['address'] = text.strip()
                        user_states[from_id]['step'] = 'edit_room'
                        if data.get('is_biznes', False):
                            send_message(vk_session_global, peer_id,
                                f"✅ Адрес сохранен: {data['address']}\n\n🚪 Введите КАБИНЕТ (или 'Оставить текущее'):",
                                get_edit_profile_keyboard())
                        else:
                            user_states[from_id]['step'] = 'edit_mall'
                            current_mall = data.get('mall_name', '')
                            if current_mall:
                                send_message(vk_session_global, peer_id,
                                    f"✅ Адрес сохранен: {data['address']}\n\n🛍 Текущий ТЦ: {current_mall}\n\nВведите НОВЫЙ ТЦ или нажмите 'Оставить текущее':",
                                    get_edit_profile_keyboard())
                            else:
                                send_message(vk_session_global, peer_id,
                                    f"✅ Адрес сохранен: {data['address']}\n\n🛍 Введите ТЦ (или 'Оставить текущее'):",
                                    get_edit_profile_keyboard())
                        continue
                    elif step == 'edit_room':
                        data['room'] = text.strip()
                        user_states[from_id]['step'] = 'edit_mall'
                        current_mall = data.get('mall_name', '')
                        if current_mall:
                            send_message(vk_session_global, peer_id,
                                f"✅ Кабинет сохранен: {data['room']}\n\n🛍 Текущий ТЦ: {current_mall}\n\nВведите НОВЫЙ ТЦ или нажмите 'Оставить текущее':",
                                get_edit_profile_keyboard())
                        else:
                            send_message(vk_session_global, peer_id,
                                f"✅ Кабинет сохранен: {data['room']}\n\n🛍 Введите ТЦ (или 'Оставить текущее'):",
                                get_edit_profile_keyboard())
                        continue
                    elif step == 'edit_mall':
                        data['mall_name'] = text.strip()
                        user_states[from_id]['step'] = 'edit_org'
                        current_org = data.get('organization', '')
                        if current_org:
                            send_message(vk_session_global, peer_id,
                                f"✅ ТЦ сохранен: {data['mall_name']}\n\n🏢 Текущая организация: {current_org}\n\nВведите НОВУЮ ОРГАНИЗАЦИЮ или нажмите 'Оставить текущее':",
                                get_edit_profile_keyboard())
                        else:
                            send_message(vk_session_global, peer_id,
                                f"✅ ТЦ сохранен: {data['mall_name']}\n\n🏢 Введите ОРГАНИЗАЦИЮ (или 'Оставить текущее'):",
                                get_edit_profile_keyboard())
                        continue
                    elif step == 'edit_org':
                        data['organization'] = text.strip()
                        save_user(from_id, data['full_name'], data['organization'], data['address'], data.get('room', ''), data.get('mall_name', ''))
                        if data.get('location_type') == 'biznes_centr':
                            add_user_to_group(from_id, 'biznes_centr')
                            remove_user_from_group(from_id, 'main')
                        else:
                            add_user_to_group(from_id, 'main')
                            remove_user_from_group(from_id, 'biznes_centr')
                        send_message(vk_session_global, peer_id, "✅ Анкета обновлена!")
                        del user_states[from_id]
                        continue
                if not is_edit:
                    if text == "🔙 назад":
                        if step == 'waiting_room':
                            user_states[from_id]['step'] = 'waiting_location'
                            send_message(vk_session_global, peer_id, "📍 Выберите место:", get_location_keyboard())
                            continue
                        elif step == 'waiting_address':
                            user_states[from_id]['step'] = 'waiting_location'
                            send_message(vk_session_global, peer_id, "📍 Выберите место:", get_location_keyboard())
                            continue
                        elif step == 'waiting_mall':
                            user_states[from_id]['step'] = 'waiting_address'
                            send_message(vk_session_global, peer_id, "📍 Введите АДРЕС:\n📌 Пример: Ул. 20-летия Победы 173В", get_back_keyboard())
                            continue
                        elif step == 'waiting_org':
                            if data.get('location_type') == 'biznes_centr':
                                user_states[from_id]['step'] = 'waiting_room'
                                send_message(vk_session_global, peer_id, "🏢 БЦ 5 звезд\n👉 Введите КАБИНЕТ:", get_back_keyboard())
                            elif data.get('mall_name', ''):
                                user_states[from_id]['step'] = 'waiting_mall'
                                send_message(vk_session_global, peer_id, f"✅ ТЦ: {data['mall_name']}\n👉 Введите ТЦ:", get_back_keyboard())
                            else:
                                user_states[from_id]['step'] = 'waiting_address'
                                send_message(vk_session_global, peer_id, "📍 Введите АДРЕС:", get_back_keyboard())
                            continue
                    if step == 'waiting_location':
                        if text == "⭐ бц 5 звезд":
                            data['location_type'] = 'biznes_centr'
                            data['address'] = 'БЦ 5 звезд'
                            user_states[from_id]['step'] = 'waiting_room'
                            send_message(vk_session_global, peer_id, "🏢 БЦ 5 звезд\n👉 Введите КАБИНЕТ:", get_back_keyboard())
                            continue
                        elif text == "📍 другое место":
                            data['location_type'] = 'other'
                            data['mall_name'] = ''
                            user_states[from_id]['step'] = 'waiting_address'
                            send_message(vk_session_global, peer_id, "📍 Введите АДРЕС:\n📌 Пример: Ул. 20-летия Победы 173В", get_back_keyboard())
                            continue
                        else:
                            send_message(vk_session_global, peer_id, "❗ Выберите вариант:", get_location_keyboard())
                            continue
                    elif step == 'waiting_room':
                        data['room'] = text.strip()
                        user_states[from_id]['step'] = 'waiting_org'
                        send_message(vk_session_global, peer_id, f"✅ Кабинет: {data['room']}\n\n👉 Введите ОРГАНИЗАЦИЮ (или 'Нет организации'):", get_org_skip_keyboard_with_back())
                        continue
                    elif step == 'waiting_address':
                        data['address'] = text.strip()
                        user_states[from_id]['step'] = 'waiting_mall'
                        send_message(vk_session_global, peer_id, "✅ Адрес сохранен!\n\n👉 Введите ТЦ:\n📌 Пример: ТЦ Улей", get_back_keyboard())
                        continue
                    elif step == 'waiting_mall':
                        data['mall_name'] = text.strip()
                        user_states[from_id]['step'] = 'waiting_org'
                        send_message(vk_session_global, peer_id, f"✅ ТЦ: {data['mall_name']}\n\n👉 Введите ОРГАНИЗАЦИЮ (или 'Нет организации'):", get_org_skip_keyboard_with_back())
                        continue
                    elif step == 'waiting_org':
                        data['organization'] = "" if text == "нет организации" else text.strip()
                        group_type = 'biznes_centr' if data.get('location_type') == 'biznes_centr' else 'main'
                        is_new = save_user(from_id, data['full_name'], data['organization'], data['address'], data.get('room', ''), data.get('mall_name', ''))
                        add_user_to_group(from_id, group_type)
                        if is_new:
                            user_data = {
                                'vk_id': from_id, 'full_name': data['full_name'],
                                'organization': data['organization'], 'address': data['address'],
                                'room': data.get('room', ''), 'mall_name': data.get('mall_name', ''),
                                'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            send_admin_notification(vk_session_global, user_data)
                            mark_notified(from_id)
                        group_names = {'main': 'Основная', 'biznes_centr': 'БЦ 5 звезд'}
                        answer = f"""🎉 АНКЕТА ЗАПОЛНЕНА!

👤 ФИО: {data['full_name']}
🔗 Ссылка: https://vk.com/id{from_id}
📍 Адрес: {data['address']}"""
                        if data.get('room', ''):
                            answer += f"\n🚪 Кабинет: {data['room']}"
                        if data.get('mall_name', ''):
                            answer += f"\n🛍 ТЦ: {data['mall_name']}"
                        if data['organization']:
                            answer += f"\n🏢 Организация: {data['organization']}"
                        answer += f"\n🏷️ Группа: {group_names.get(group_type, 'Основная')}\n\n✅ Данные сохранены!"
                        send_message(vk_session_global, peer_id, answer)
                        del user_states[from_id]
                        continue
                    continue

            # НЕИЗВЕСТНАЯ КОМАНДА
            if text:
                user = get_user(from_id)
                keyboard = get_admin_menu_keyboard() if is_admin(from_id) else (None if user else get_main_with_fill_keyboard())
                send_message(vk_session_global, peer_id, f"❓ Я не знаю команду '{text}'\n\nНажмите '🏠 Меню'", keyboard)

except Exception as e:
    print(f"❌ Ошибка: {e}")
