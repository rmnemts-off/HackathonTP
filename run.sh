#!/bin/bash

INBOX_DIR="${1:-inbox}"

echo "==============================="
echo "  Запуск обработки почты"
echo "==============================="
echo "Папка с письмами: $INBOX_DIR"
echo ""

python email_parser_and_classifier.py "$INBOX_DIR"
EXIT_CODE=$?

echo ""
echo "==============================="

if [ $EXIT_CODE -eq 0 ]; then
    echo "  СТАТУС: УСПЕШНО"
    echo ""

    if [ -f "output/classified.json" ]; then
        TOTAL=$(python -c "import json; data=json.load(open('output/classified.json', encoding='utf-8')); print(len(data))")
        echo "  Обработано писем: $TOTAL"

        echo ""
        echo "  Категории:"
        python -c "
import json
from collections import Counter
data = json.load(open('output/classified.json', encoding='utf-8'))
cats = []
for item in data:
    cats.extend(item.get('categories', []))
for cat, count in sorted(Counter(cats).items(), key=lambda x: -x[1]):
    print(f'    {cat}: {count}')
"
    fi

    if [ -f "output/trash.txt" ]; then
        TRASH=$(wc -l < "output/trash.txt")
        echo ""
        echo "  Файлов в корзине: $TRASH"
    fi
else
    echo "  СТАТУС: ОШИБКА (код $EXIT_CODE)"
fi

echo "==============================="