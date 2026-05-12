import json
import random
import os
import pymorphy3
import re
import logging

morph = pymorphy3.MorphAnalyzer()

class BotCore:
    def __init__(self, scn_dir):
        self.scn_dir = scn_dir
        self.scns = {} 
        self._load_all()
        
        self.user_st = {}  
        self.user_rep = {} 
        self.curr_scn = {} 
        self.user_vuln = {}

    def _load_all(self):
        for f_name in os.listdir(self.scn_dir):
            if f_name.endswith(".json"):
                with open(os.path.join(self.scn_dir, f_name), "r", encoding="utf-8") as f:
                    self.scns[f_name] = json.load(f)

    def set_scn(self, u_id, f_name):
        self.curr_scn[u_id] = f_name
        scn_data = self.scns[f_name]
        self.user_st[u_id] = scn_data["initial_state"]
        self.user_rep[u_id] = 0
        self.user_vuln[u_id] = 0
        return self._get_state_text(u_id, scn_data["initial_state"])

    def set_random_scn(self, u_id):
        f_name = random.choice(list(self.scns.keys()))
        return self.set_scn(u_id, f_name)

    def _get_lemma(self, text):
        res = re.sub(r'[^\w\s]', '', text.lower())
        return morph.parse(res)[0].normal_form if res else ""

    def _check_keyw(self, msg, keyw):
        user_words = msg.split()
        user_lemmas = [self._get_lemma(w) for w in user_words]
        for k in keyw:
            k_lemma = self._get_lemma(k)
            if k_lemma in user_lemmas:
                return True
        return False

    def _get_state_text(self, u_id, st_id):
        scn_name = self.curr_scn.get(u_id)
        if not scn_name or scn_name not in self.scns:
            return "⚠ Сценарий не найден. Напишите 'старт'."

        scn_data = self.scns[scn_name]
        state = scn_data["states"].get(st_id)
        
        if not state:
            return f"⚠ Ошибка: состояние '{st_id}' не описано в JSON."

        raw_text = state.get("text", "")
        if not raw_text:
            return f"⚠ Внимание: в состоянии '{st_id}' забыли написать текст!"

        if isinstance(raw_text, list):
            raw_text = "\n".join(raw_text)

        try:
            return raw_text.format(vulnerability=self.user_vuln.get(u_id, 0))
        except (KeyError, IndexError, ValueError):
            logging.warning(f"Ошибка форматирования текста в состоянии {st_id}")
            return raw_text

    def proc_msg(self, u_id, msg):
        msg = msg.lower().strip()
        scn_name = self.curr_scn.get(u_id)
        
        if not scn_name: 
            return "Ошибка: Сценарий не выбран."

        scn_data = self.scns[scn_name]
        cur_id = self.user_st.get(u_id)
        st = scn_data["states"].get(cur_id)

        if not st:
            return f"Критическая ошибка: Текущее состояние '{cur_id}' не найдено."

        next_st_id = None

        # --- 1. ОБЫЧНЫЙ ПОИСК ПЕРЕХОДА ПО КЛЮЧЕВЫМ СЛОВАМ ---
        for t in st.get("transitions", []):
            if self._check_keyw(msg, t["keywords"]):
                add_val = t.get("vulnerability_add", 0)
                self.user_vuln[u_id] = self.user_vuln.get(u_id, 0) + add_val
                next_st_id = t["next_state"]
                break

        # --- 2. ЕСЛИ КЛЮЧЕВОЕ СЛОВО НЕ НАЙДЕНО ---
        if not next_st_id:
            df = st.get("default_transition")
            if df:
                self.user_rep[u_id] = self.user_rep.get(u_id, 0) + 1
                alt_st = df.get("alternative_state")
                if self.user_rep[u_id] >= df.get("max_repeats", 2) and alt_st:
                    next_st_id = alt_st
                    self.user_rep[u_id] = 0
                else:
                    return self._get_state_text(u_id, cur_id)
            else:
                return "Я вас не совсем понял. Попробуйте ответить иначе."

        # --- 3. ПРОВЕРКА УСЛОВНЫХ СОСТОЯНИЙ (CONDITIONAL STATES) ---
        cond_rules = scn_data.get("conditional_states", {}).get("check_vulnerability", {}).get("rules", [])
        sorted_rules = sorted(cond_rules, key=lambda x: x.get("priority", 99))
        current_vuln = self.user_vuln.get(u_id, 0)

        for rule in sorted_rules:
            cond_str = rule["condition"].replace("vulnerability", str(current_vuln))
            try:
                if eval(cond_str):
                    if rule["next_state"]:
                        next_st_id = rule["next_state"]
                    break 
            except Exception as e:
                logging.error(f"Ошибка в вычислении условия {cond_str}: {e}")

        self.user_st[u_id] = next_st_id
        return self._get_state_text(u_id, next_st_id)