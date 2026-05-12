
############ ИМПОРТЫ И НАСТРОЙКИ ############

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from bot_core import BotCore
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import os
import logging
from logging.handlers import RotatingFileHandler
import json
from dotenv import load_dotenv
load_dotenv()


# Настройки доступа
TOKEN = os.getenv("VK_TOKEN")
ADMINS = [479412087, 626597056]
SCN = "."

# Инициализация
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)
core = BotCore(SCN)

#логгинг
log_handler = RotatingFileHandler('bot_security.log', maxBytes=5*1024*1024, backupCount=5)
logging.basicConfig(
    handlers=[log_handler],
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)


############ КЛАВИАТУРА ############



def get_start_kb():
    kb = VkKeyboard(one_time=True)
    kb.add_button("Начать сценарий", color=VkKeyboardColor.POSITIVE)
    return kb.get_keyboard()

def get_game_kb():
    kb = VkKeyboard(inline=False) # Обычная клавиатура внизу
    kb.add_button("Завершить принудительно", color=VkKeyboardColor.NEGATIVE, payload={"cmd": "stop_game"})
    return kb.get_keyboard()

def get_admin_kb():
    kb = VkKeyboard(inline=True) # Маленькая кнопка прямо в сообщении
    files = [f for f in os.listdir(SCN) if f.endswith(".json")]

    MAX_BUTTONS_PER_ROW = 3

    for i, f in enumerate(files):
        kb.add_button(f, color=VkKeyboardColor.PRIMARY, payload={"cmd": "set_scn", "name": f})
        if (i + 1) % MAX_BUTTONS_PER_ROW == 0 and (i + 1) != len(files): 
            kb.add_line() # По 2 кнопки в ряд
    return kb.get_keyboard()



############ ДИСПЕТЧЕР ############



for ev in longpoll.listen():
    if ev.type == VkEventType.MESSAGE_NEW and ev.to_me:
        u_id = ev.user_id
        txt = ev.text.lower().strip()
        
        # Пытаемся достать команду из кнопки (payload)
        import json
        payload = json.loads(ev.extra_values.get('payload', '{}'))
        cmd = payload.get('cmd')

        # --- УРОВЕНЬ 1: СИСТЕМНЫЕ КОМАНДЫ (АДМИН/ВАНИШ) ---
        if txt == "админ":
            if u_id in ADMINS:
                vk.messages.send(user_id=u_id, message="Выбери сценарий:", random_id=0, keyboard=get_admin_kb())
            else:
                vk.messages.send(user_id=u_id, message="Доступ запрещен.", random_id=0)
            continue

        if cmd == "set_scn":
            ans = core.set_scn(u_id, payload['name'])
            vk.messages.send(user_id=u_id, message=ans, random_id=0, keyboard=get_game_kb())
            logging.info(f"UID: {u_id} | Action: SET_SCENARIO | File: {payload['name']}")
            continue

        if txt == "ваниш":
            core.curr_scn.pop(u_id, None) # Стираем память о сценарии
            vk.messages.send(user_id=u_id, message="Система сброшена.", random_id=0, keyboard=get_start_kb())
            continue

        # --- УРОВЕНЬ 2: УПРАВЛЕНИЕ ИГРОЙ (СТАРТ/СТОП) ---
        if txt == "начать сценарий" or txt == "старт":
            ans = core.set_random_scn(u_id)
            vk.messages.send(user_id=u_id, message=ans, random_id=0, keyboard=get_game_kb())
            logging.info(f"UID: {u_id} | Action: START_GAME")
            continue

        if cmd == "stop_game":
            core.curr_scn.pop(u_id, None)
            vk.messages.send(user_id=u_id, message="Игра прервана.", random_id=0, keyboard=get_start_kb())
            continue

        # --- УРОВЕНЬ 3: ИГРОВОЙ ПРОЦЕСС ---
        # Если юзер в сценарии — отправляем текст в ядро
        if u_id in core.curr_scn:
            try:
                ans = core.proc_msg(u_id, ev.text)
                
                # Проверяем, не закончилась ли игра после этого ответа
                scn = core.curr_scn.get(u_id)
                st_id = core.user_st.get(u_id)
                is_final = core.scns[scn]['states'][st_id].get('is_final')
                
                kb = get_start_kb() if is_final else get_game_kb()
                if is_final: 
                    logging.info(f"UID: {u_id} | Action: REACHED_FINAL | Scenario: {scn}")
                    core.curr_scn.pop(u_id, None) # Чистим после финала
            
                vk.messages.send(user_id=u_id, message=ans, random_id=0, keyboard=kb)
            except Exception as e:
                logging.error(f"CRITICAL ERROR: {e}")
                vk.messages.send(user_id=u_id, message="Ой! В сценарии ошибка. Админ уже в курсе.", random_id=0)
        else:
            # Если юзер не в игре и пишет ерунду
            vk.messages.send(user_id=u_id, message="Нажми 'Начать сценарий', чтобы запустить тренажер.", random_id=0, keyboard=get_start_kb())