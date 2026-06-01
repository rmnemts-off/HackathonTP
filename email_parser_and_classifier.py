from __future__ import annotations
import sys
import os
import json
import email
import re
from pathlib import Path
from datetime import datetime
import pymorphy3
from razdel import tokenize as razdel_tokenize


class EmailProcessor:

    def __init__(self):
        self.morph = pymorphy3.MorphAnalyzer()

    def parse(self, path: Path) -> dict:
        raw = path.read_text(encoding="utf-8", errors="replace")

        header_map = [
            (r"^От кого:", "From:"), (r"^Кому:", "To:"),
            (r"^Дата:", "Date:"), (r"^Тема:", "Subject:"),
            (r"^ot kogo:", "From:"), (r"^komu:", "To:"),
            (r"^data:", "Date:"), (r"^tema:", "Subject:"),
            (r"^theme:", "Subject:"), (r"^subject:", "Subject:"),
            (r"^from:", "From:"), (r"^to:", "To:"), (r"^date:", "Date:"),
        ]
        text = raw
        for pattern, replacement in header_map:
            text = re.sub(pattern, replacement, text, flags=re.MULTILINE | re.IGNORECASE)

        msg = email.message_from_string(text)
        return {
            "subject": msg["subject"] or "",
            "from": msg["from"] or "",
            "to": msg["to"] or None,
            "body": msg.get_payload() or "",
            "date": msg.get("date") or None,
        }

    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return "\n".join(line.rstrip() for line in text.splitlines()).strip()

    def lemmatize(self, text: str) -> list[str]:
        if not text:
            return []
        lemmas = []
        for tok in razdel_tokenize(text):
            word = tok.text.lower()
            if not re.match(r"[а-яёa-z]{2,}", word):
                continue
            parses = self.morph.parse(word)
            lemmas.append(parses[0].normal_form if parses else word)
        return lemmas

    def process_file(self, file_path: Path, current_date: str) -> dict:
        parsed = self.parse(file_path)
        subj_nrm = self.normalize(parsed["subject"])
        body_nrm = self.normalize(parsed["body"])
        return {
            "source_file": file_path.name,
            "path": str(file_path.absolute()),
            "subject_nrm": subj_nrm,
            "body_nrm": body_nrm,
            "from": parsed["from"].lower() if parsed["from"] else "",
            "to": parsed["to"].lower() if parsed["to"] else None,
            "subject_lemm": self.lemmatize(subj_nrm),
            "body_lemm": self.lemmatize(body_nrm),
            "time": parsed["date"] or current_date,
        }

    def process_directory(self, directory_path: str) -> tuple[list[dict], list[Path]]:
        emails_dir = Path(directory_path)
        if not emails_dir.is_dir():
            raise NotADirectoryError(f"{directory_path} не является директорией")

        results, trash = [], []
        current_date = datetime.now().isoformat()

        for file_path in emails_dir.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() != ".txt":
                trash.append(file_path)
                continue
            try:
                results.append(self.process_file(file_path, current_date))
            except Exception:
                trash.append(file_path)

        return results, trash

    @staticmethod
    def move_processed_files(results: list[dict], base_output_dir: Path):
        for item in results:
            path = Path(item["path"])
            if not path.exists():
                print(f"Файл не найден: {path}")
                continue
            for category in item.get("categories", ["Прочее"]):
                category_dir = base_output_dir / category
                category_dir.mkdir(parents=True, exist_ok=True)
                dest = category_dir / path.name
                if len(item["categories"]) > 1:
                    import shutil
                    shutil.copy2(path, dest)
                else:
                    path.rename(dest)
                print(f"Перемещён: {path.name} → {category}/")
            if path.exists():
                path.unlink()


class MailClassifier:

    _DEVICE_LEMMS = {
        "гарнитура", "ноутбук", "принтер", "сканер", "мышь",
        "монитор", "клавиатура", "устройство", "оборудование",
    }

    @staticmethod
    def in_lemm(lemms: list[str], *words: str) -> bool:
        s = set(lemms)
        return any(w in s for w in words)

    @staticmethod
    def all_in_lemm(lemms: list[str], *words: str) -> bool:
        s = set(lemms)
        return all(w in s for w in words)

    @staticmethod
    def in_text(text: str, *phrases: str) -> bool:
        t = (text or "").lower()
        return any(p in t for p in phrases)

    @staticmethod
    def all_in_text(text: str, *phrases: str) -> bool:
        t = (text or "").lower()
        return all(p in t for p in phrases)

    @classmethod
    def has_device_lemm(cls, lemms: list[str]) -> bool:
        return bool(cls._DEVICE_LEMMS & set(lemms))

    @staticmethod
    def is_draft(subj_raw: str, body_raw: str, to: str | None) -> bool: #делал Эрик
        subj_empty = not (subj_raw or "").strip() or (subj_raw or "").lower().strip() in ("re:", "fwd:")
        body_empty = not (body_raw or "").strip()
        if subj_empty and body_empty:
            return True
        if not to and body_empty:
            return True
        return False

    @staticmethod
    def is_outgoing(from_addr: str) -> bool:
        return "it-support@company.ru" in (from_addr or "").lower()

    @classmethod
    def is_spam(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делал Эрик
        if cls.in_lemm(s_lemm, "розыгрыш", "акция", "скидка"):
            return True
        if cls.in_text(s_nrm,
            "вы выиграли", "подтвердите личность", "верификация аккаунта",
            "аккаунт будет заблокирован", "exclusive offer", "срочно подтвердите",
        ):
            return True
        if cls.in_text(b_nrm,
            "введите данные карты", "данные банковской карты",
            "вы стали победителем", "cdn-service.net",
            "secure-login-verify", "totally-not-spam",
        ):
            return True
        if cls.in_text(b_nrm, "введите логин и пароль") and cls.in_text(b_nrm, "http"):
            return True
        if cls.all_in_text(b_nrm, "подозрительный вход", "подтвердите личность"):
            return True
        if cls.in_text(b_nrm, "только сегодня") and cls.in_lemm(b_lemm, "скидка", "акция"):
            return True
        if cls.in_text(b_nrm, "перейдите по ссылке") and cls.in_text(b_nrm, "доступ будет заблокирован", "пароль истекает"):
            return True
        return False

    @classmethod
    def is_incident(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делала Соня
        if cls.in_text(b_nrm, "отчёт мониторинга"):
            return False
        if cls.in_lemm(s_lemm, "urgent", "critical", "срочно") and not cls.in_lemm(s_lemm, "больничный", "отпуск", "встреча", "созвон"):
            return True
        if cls.in_text(s_nrm,
            "критичный инцидент", "критический инцидент", "массовый сбой",
            "работа остановлена", "не отвечает", "ошибка 500",
            "у всех отдела", "у всего отдела", "[critical]", "недоступен", "у моего отдела", "клиент"
        ):
            return True
        if cls.in_text(s_nrm, "не работает") and cls.in_lemm(s_lemm, "система", "сервис", "портал", "directory", "desk"):
            return True
        if cls.in_lemm(s_lemm, "падать") and cls.in_lemm(s_lemm, "система", "сервис", "портал", "desk"):
            return True
        if cls.in_text(s_nrm, "не могу войти") and cls.in_text(s_nrm, "у всех", "у всего"):
            return True
        if cls.in_lemm(s_lemm, "срочно") and cls.in_text(s_nrm, "не работает"):
            return True
        if cls.in_text(b_nrm,
            "критичный инцидент", "критический инцидент", "ошибка 500",
            "работа остановлена", "работа полностью остановлена",
            "нужна срочная помощь", "у всего отдела", "у всех отдела",
            "не отвечает", "по-прежнему недоступен", "нужен статус",
            "ошибка появляется сразу при входе", "у моего отдела", "клиент"
        ):
            return True
        if cls.all_in_lemm(b_lemm, "затронуть", "сотрудник"):
            return True
        if cls.all_in_text(b_nrm, "обращаемся повторно", "нужен статус"):
            return True
        if cls.in_text(b_nrm, "перестал открываться") and cls.in_lemm(b_lemm, "отдел", "сотрудник"):
            return True
        if cls.in_text(b_nrm, "несколько коллег") and cls.in_lemm(b_lemm, "подтвердить"):
            return True
        if cls.in_lemm(b_lemm, "кнопка") and cls.in_text(b_nrm, "не работает"):
            return True
        if cls.in_text(b_nrm, "не может зарегистрироваться") and cls.in_lemm(b_lemm, "клиент", "портал"):
            return True
        return False

    @classmethod
    def is_access(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делал Эрик
        if cls.in_text(s_nrm,
            "запрос доступа", "нет доступа", "нет прав",
            "нужны права", "выдать доступ", "выдать права", "запрос прав",
        ):
            return True
        if cls.in_text(s_nrm, "после перевода") and cls.in_lemm(s_lemm, "доступ", "право"):
            return True
        if cls.in_text(s_nrm, "новый сотрудник", "временный сотрудник") and cls.in_lemm(s_lemm, "доступ", "право"):
            return True
        if cls.in_lemm(b_lemm, "доступ") and cls.in_lemm(b_lemm, "выдать", "нужный", "подготовить", "восстановить", "пропасть"):
            return True
        if cls.in_lemm(b_lemm, "право") and cls.in_lemm(b_lemm, "выдать", "нужный"):
            return True
        if cls.in_text(b_nrm,
            "уровень доступа", "только чтение", "пропал доступ",
            "прошу восстановить", "новый сотрудник приступает",
            "временный сотрудник", "доступ требуется на",
            "пересмотреть уровни доступа",
            "подготовить рабочее место и доступы",
        ):
            return True
        if cls.in_text(b_nrm, "после перевода") and cls.in_lemm(b_lemm, "доступ", "право"):
            return True
        return False

    @classmethod
    def is_software(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делала Соня
        if cls.in_lemm(s_lemm, "браузер"):
            return True
        if cls.in_text(s_nrm, "ошибка в", "не запускается", "проблема с установкой", "зависает при открытии"):
            return True
        if cls.in_text(s_nrm, "после обновления") and cls.in_lemm(s_lemm, "zoom", "chrome", "google"):
            return True
        if cls.in_lemm(b_lemm, "chrome", "zoom"):
            return True
        if cls.in_text(b_nrm,
            "не открывает файлы", "перестал запускаться", "не могу установить",
            "выдаёт ошибку", "переустановка не помогла",
            "после обновления системы", "ошибка при старте"
        ) or (cls.in_text(b_nrm, "не работает") and cls.in_text("по", "приложение", "утилита")):
            return True
        if cls.in_text(b_nrm, "установщик") and cls.in_lemm(b_lemm, "зависать"):
            return True
        return False

    @classmethod
    def is_hardware(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делала Соня
        if cls.has_device_lemm(s_lemm) and cls.in_text(s_nrm, "неисправность", "сломался", "нужна замена", "ремонт", "проблема с"):
            return True
        if cls.in_text(b_nrm,
            "заявка на ремонт", "перестал работать после падения",
            "не определяется системой", "издаёт посторонние звуки",
            "организовать диагностику", "организовать замену", "сломался экран",
        ):
            return True
        if cls.in_text(b_nrm, "зависает при работе") and cls.has_device_lemm(b_lemm):
            return True
        if cls.has_device_lemm(b_lemm) and cls.in_text(b_nrm, "не включается"):
            return True
        if cls.in_text(b_nrm, "не работает") and cls.has_device_lemm(b_lemm):
            return True
        return False

    @classmethod
    def is_financial(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делала Маша
        if cls.in_lemm(s_lemm, "счёт", "счет", "акт", "оплата"):
            return True
        if cls.in_text(s_nrm,
            "закрывающие документы", "уточнение по оплате",
            "счёт на оплату", "счет на оплату", "акт выполненных работ",
        ):
            return True
        if cls.in_lemm(b_lemm, "бухгалтерия"):
            return True
        if cls.in_text(b_nrm,
            "статус оплаты", "уточните статус оплаты",
            "оплата по договору", "передать в бухгалтерию",
            "оказанные услуги", "закрывающие документы",
            "счёт и акт", "счет и акт",
        ):
            return True
        if cls.in_text(b_nrm, "высылаем") and cls.in_lemm(b_lemm, "закрывать"):
            return True
        if cls.in_text(b_nrm, "направляем") and cls.in_lemm(b_lemm, "закрывать"):
            return True
        if cls.in_text(b_nrm, "подтвердить получение") and cls.in_lemm(b_lemm, "счёт", "счет"):
            return True
        if cls.in_lemm(b_lemm, "оплата") and cls.in_text(b_nrm, "не отражена", "ещё не отражена"):
            return True
        return False

    @classmethod
    def is_legal(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делала Маша
        if cls.is_hardware(s_lemm, s_nrm, b_lemm, b_nrm) or cls.is_software(s_lemm, s_nrm, b_lemm, b_nrm) or cls.is_access(s_lemm, s_nrm, b_lemm, b_nrm):
            return False
        if cls.in_lemm(s_lemm, "правка"):
            return True
        # "договор" в теме — не юр., если рядом финансовый контекст ("оплата по договору" и т.п.)
        if cls.in_lemm(s_lemm, "договор") and not cls.in_lemm(s_lemm, "оплата", "счёт", "акт"):
            return True
        # "согласование" в теме — не юр., если речь о системе/сервисе ("система согласования")
        if cls.in_lemm(s_lemm, "согласование") and not cls.in_lemm(s_lemm, "система", "сервис"):
            return True
        if cls.in_text(s_nrm, "тз", "техническое задание", "инструкция на согласование", "финальная версия"):
            return True
        if cls.in_lemm(b_lemm, "реквизит"):
            return True
        if cls.in_text(b_nrm,
            "направляем на согласование", "направляем инструкцию на согласование",
            "просим проверить условия", "вернуть с правками или подписью",
            "расхождение в реквизитах", "финальная версия договора",
        ):
            return True
        if cls.all_in_text(b_nrm, "новая версия", "с учётом ваших комментариев"):
            return True
        if cls.all_in_text(b_nrm, "новая версия", "с учётом") and cls.in_lemm(b_lemm, "договор", "инструкция", "тз"):
            return True
        if cls.in_lemm(b_lemm, "договор") and cls.in_text(b_nrm, "получен и принят в работу", "получен и принята в работу"):
            return True
        if cls.in_lemm(b_lemm, "инструкция") and cls.in_text(b_nrm, "получена и принята в работу", "получен и принят в работу"):
            return True
        if cls.in_lemm(b_lemm, "подтвердить") and cls.in_text(b_nrm, "получение договора", "что договор получен", "что инструкция получен"):
            return True
        return False

    @classmethod
    def is_hr(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делала Маша
        if cls.in_lemm(s_lemm, "отпуск", "больничный"):
            return True
        if cls.in_text(s_nrm,
            "больничный лист", "изменение графика работы",
            "оформление нового сотрудника", "izmenenie grafika raboty",
        ):
            return True
        if cls.in_lemm(b_lemm, "нетрудоспособность", "нетрудоспособности", "netrudosposobnosti", "bolnichnyy"):
            return True
        if cls.in_text(b_nrm,
            "прошу согласовать ежегодный отпуск", "согласовать ежегодный отпуск",
            "направляю больничный лист", "napravlyayu bolnichnyy list",
            "период нетрудоспособности", "dlya vneseniya v sistemu",
        ):
            return True
        if cls.in_text(b_nrm, "для внесения в систему") and cls.in_lemm(b_lemm, "больничный", "отпуск"):
            return True
        return False

    @classmethod
    def is_meeting(cls, s_lemm: list[str], s_nrm: str, b_lemm: list[str], b_nrm: str) -> bool: #делала Соня
        if cls.in_lemm(s_lemm, "созвон", "встреча", "митинг", "демо", "перенос", "приглашение"):
            return True
        if cls.in_text(s_nrm, "статус задач"):
            return True
        if cls.in_text(s_nrm, "обсудить") and cls.in_lemm(s_lemm, "задача", "статус"):
            return True
        # "дть" — лемма слова "демо" в pymorphy3 - наша заплатка)
        if cls.in_lemm(b_lemm, "созвон", "встреча", "митинг", "демо", "дть"):
            return True
        if cls.in_text(b_nrm, "нужно обсудить", "давайте обсудим", "подтвердите участие"):
            return True
        return False

    def classify(self, record: dict) -> list[str]:
        subj_nrm = record.get("subject_nrm") or ""
        body_nrm = record.get("body_nrm") or ""
        subj_lemm = record.get("subject_lemm") or []
        body_lemm = record.get("body_lemm") or []
        from_addr = record.get("from") or ""
        to_addr = record.get("to") or ""

        if self.is_draft(subj_nrm, body_nrm, to_addr):
            return ["Черновик"]
        if self.is_outgoing(from_addr):
            return ["Исходящие"]
        if self.is_spam(subj_lemm, subj_nrm, body_lemm, body_nrm):
            return ["Спам"]

        args = (subj_lemm, subj_nrm, body_lemm, body_nrm)
        checks = [
            ("Инциденты", self.is_incident),
            ("Доступ", self.is_access),
            ("ПО", self.is_software),
            ("Оборудование", self.is_hardware),
            ("Фин. вопросы", self.is_financial),
            ("Юр. вопросы", self.is_legal),
            ("HR", self.is_hr),
            ("Встречи", self.is_meeting),
        ]
        categories = [label for label, fn in checks if fn(*args)]
        return categories or ["Прочее"]

    def classify_all(self, records: list[dict]) -> list[dict]:
        for r in records:
            r["categories"] = self.classify(r)
        return records


if __name__ == "__main__":
    path_to_emails = (
        sys.argv[1]
        if len(sys.argv) > 1
        else input("Введите путь к директории: ")
    )

    processor = EmailProcessor()
    classifier = MailClassifier()

    try:
        results, trash = processor.process_directory(path_to_emails)
    except NotADirectoryError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    classified = classifier.classify_all(results)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    (output_dir / "classified.json").write_text(
        json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "trash.txt").open("w", encoding="utf-8") as f:
        f.writelines(f"{p}\n" for p in trash)

    print(f"Готово: {len(classified)} писем → output/classified.json, {len(trash)} в trash")

    processor.delete_processed_files(classified)
