import pytest

from email_parser_and_classifier import EmailProcessor, MailClassifier


@pytest.fixture
def processor():
    return EmailProcessor()


@pytest.fixture
def classifier():
    return MailClassifier()


@pytest.mark.parametrize(
    "subject, body",
    [
        ("Вы выиграли приз", ""),
        ("Срочно подтвердите личность", ""),
        ("", "Введите данные карты на сайте"),
    ]
)
def test_spam(processor, subject, body):
    subject_lemm = processor.lemmatize(subject)
    body_lemm = processor.lemmatize(body)

    result = MailClassifier.is_spam(
        subject_lemm,
        subject,
        body_lemm,
        body
    )

    assert result


@pytest.mark.parametrize(
    "subject, body",
    [
        ("Критический инцидент", ""),
        ("Срочно! система не отвечает", ""),
        ("", "Ошибка 500. Работа остановлена"),
    ]
)
def test_incident(processor, subject, body):
    subject_lemm = processor.lemmatize(subject)
    body_lemm = processor.lemmatize(body)

    result = MailClassifier.is_incident(
        subject_lemm,
        subject,
        body_lemm,
        body
    )

    assert result


@pytest.mark.parametrize(
    "subject, body",
    [
        ("Запрос доступа к системе", ""),
        ("Нет прав на редактирование", ""),
        ("", "Прошу восстановить доступ"),
    ]
)
def test_access(processor, subject, body):
    subject_lemm = processor.lemmatize(subject)
    body_lemm = processor.lemmatize(body)

    result = MailClassifier.is_access(
        subject_lemm,
        subject,
        body_lemm,
        body
    )

    assert result


@pytest.mark.parametrize(
    "subject, body",
    [
        ("Проблема с установкой Zoom", ""),
        ("Браузер не запускается", ""),
        ("", "Переустановка не помогла"),
    ]
)
def test_software(processor, subject, body):
    subject_lemm = processor.lemmatize(subject)
    body_lemm = processor.lemmatize(body)

    result = MailClassifier.is_software(
        subject_lemm,
        subject,
        body_lemm,
        body
    )

    assert result


@pytest.mark.parametrize(
    "subject, body",
    [
        ("Принтер сломался", ""),
        ("Неисправность ноутбука", ""),
        ("", "Монитор не работает"),
    ]
)
def test_hardware(processor, subject, body):
    subject_lemm = processor.lemmatize(subject)
    body_lemm = processor.lemmatize(body)

    result = MailClassifier.is_hardware(
        subject_lemm,
        subject,
        body_lemm,
        body
    )

    assert result


@pytest.mark.parametrize(
    "subject, body",
    [
        ("Счёт на оплату", ""),
        ("Акт выполненных работ", ""),
        ("", "Уточните статус оплаты"),
    ]
)
def test_financial(processor, subject, body):
    subject_lemm = processor.lemmatize(subject)
    body_lemm = processor.lemmatize(body)

    result = MailClassifier.is_financial(
        subject_lemm,
        subject,
        body_lemm,
        body
    )

    assert result


@pytest.mark.parametrize(
    "subject, body",
    [
        ("Договор на согласование", ""),
        ("Финальная версия договора", ""),
    ]
)
def test_legal(processor, subject, body):
    subject_lemm = processor.lemmatize(subject)
    body_lemm = processor.lemmatize(body)

    result = MailClassifier.is_legal(
        subject_lemm,
        subject,
        body_lemm,
        body
    )

    assert result


def test_no_category(processor, classifier):
    record = {
        "subject_nrm": "Привет",
        "body_nrm": "Как дела? Давно не виделись, заходи в гости.",
        "from": "friend@mail.ru",
        "to": "user@company.ru"
    }

    record["subject_lemm"] = processor.lemmatize(record["subject_nrm"])
    record["body_lemm"] = processor.lemmatize(record["body_nrm"])

    categories = classifier.classify(record)
    assert categories == ["Прочее"]


def test_classify_priority_order(processor, classifier):
    draft_record = {
        "subject_nrm": "КРИТИЧЕСКИЙ ИНЦИДЕНТ ВЫ ВЫИГРАЛИ",
        "body_nrm": "",
        "from": "user@company.ru",
        "to": None
    }

    draft_record["subject_lemm"] = processor.lemmatize(draft_record["subject_nrm"])
    draft_record["body_lemm"] = []

    assert classifier.classify(draft_record) == ["Черновик"]

    outgoing_record = {
        "subject_nrm": "АКЦИЯ СКИДКА",
        "body_nrm": "Вам доступна скидка",
        "from": "it-support@company.ru",
        "to": "client@mail.ru"
    }
    outgoing_record["subject_lemm"] = processor.lemmatize(outgoing_record["subject_nrm"])
    outgoing_record["body_lemm"] = processor.lemmatize(outgoing_record["body_nrm"])

    assert classifier.classify(outgoing_record) == ["Исходящие"]


def test_empty_draft():
    result = MailClassifier.is_draft(
        "",
        "",
        None
    )

    assert result


def test_re_draft():
    result = MailClassifier.is_draft(
        "Re:",
        "",
        "user@company.ru"
    )

    assert result


def test_outgoing():
    result = MailClassifier.is_outgoing(
        "it-support@company.ru"
    )

    assert result


def test_not_spam(processor):
    subject = "Встреча в пятницу"
    body = "Давайте обсудим проект"

    subject_lemm = processor.lemmatize(subject)
    body_lemm = processor.lemmatize(body)

    result = MailClassifier.is_spam(
        subject_lemm,
        subject,
        body_lemm,
        body
    )

    assert not result


def test_empty_lemmatize(processor):
    result = processor.lemmatize("")

    assert result == []


def test_empty_normalize():
    result = EmailProcessor.normalize("")

    assert result == ""


def test_invalid_directory(processor):
    with pytest.raises(NotADirectoryError):
        processor.process_directory(
            "folder_that_does_not_exist"
        )


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Привет,    как дела?\n\n\n\nНовая строка.   ",
            "привет, как дела?\n\nновая строка."
        ),
        (
            "",
            ""
        ),
        (
            "   \n\n   \n   ",
            ""
        ),
        (
            "Текст\tс\tтабуляцией",
            "текст с табуляцией"
        ),
        (
            "Строка 1   \nСтрока 2  \nСтрока 3 ",
            "строка 1\nстрока 2\nстрока 3"
        ),
        (
            "Привет, мир!\nВсё отлично.",
            "привет, мир!\nвсё отлично."
        ),
    ]
)
def test_normalize_whitespace(processor, text, expected):
    assert processor.normalize(text) == expected


def test_non_txt_file(processor, tmp_path):
    file = tmp_path / "test.pdf"
    file.write_text("test")

    results, trash = processor.process_directory(str(tmp_path))

    assert len(results) == 0
    assert len(trash) == 1
