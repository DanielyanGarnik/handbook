#!/usr/bin/env bash
# Собирает страницы GitHub Wiki из документации репозитория.
#
#   bash scripts/sync-wiki.sh <выходная-директория>
#
# Источник правды — файлы в репозитории. Wiki генерируется из них и полностью
# перезаписывается, поэтому править страницы прямо в Wiki бессмысленно.
#
# Безопасность: в Wiki попадают только файлы, которые отслеживаются git.
# docs/CRITIQUE.md исключён через .git/info/exclude, поэтому он не может уехать
# в публичную Wiki даже случайно — проверка ниже его отсеет.

set -euo pipefail

OUT="${1:-}"
if [ -z "$OUT" ]; then
    echo "usage: $0 <output-dir>" >&2
    exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mkdir -p "$OUT"
rm -f "$OUT"/*.md

# источник -> имя страницы в Wiki
PAGES="
README.md|Home
docs/ROADMAP.md|Roadmap
docs/HOMEWORK-01.md|Homework-01
docs/HOMEWORK-02.md|Homework-02
docs/LESSON-02.md|Lesson-02
docs/TEAM-SKILLS.md|Team-Skills
docs/IDEA-PIPELINE.md|Idea-Pipeline
docs/telegram-messages.md|Telegram-Messages
templates/idea-card.md|Idea-Card
templates/idea-card.hy.md|Idea-Card-HY
templates/idea-card.en.md|Idea-Card-EN
"

# Переписывает ссылки вида ](path/file.md#anchor) в плоские имена страниц Wiki.
# Правится только содержимое markdown-ссылок, текст и код-спаны не трогаются.
rewrite_links() {
    sed -E \
        -e 's#\]\(\.\./#](#g' \
        -e 's#\]\(\./#](#g' \
        -e 's#\]\(docs/#](#g' \
        -e 's#\]\(templates/#](#g' \
        -e 's#\]\(README\.md#](Home#g' \
        -e 's#\]\(ROADMAP\.md#](Roadmap#g' \
        -e 's#\]\(HOMEWORK-01\.md#](Homework-01#g' \
        -e 's#\]\(HOMEWORK-02\.md#](Homework-02#g' \
        -e 's#\]\(LESSON-02\.md#](Lesson-02#g' \
        -e 's#\]\(TEAM-SKILLS\.md#](Team-Skills#g' \
        -e 's#\]\(IDEA-PIPELINE\.md#](Idea-Pipeline#g' \
        -e 's#\]\(telegram-messages\.md#](Telegram-Messages#g' \
        -e 's#\]\(idea-card\.hy\.md#](Idea-Card-HY#g' \
        -e 's#\]\(idea-card\.en\.md#](Idea-Card-EN#g' \
        -e 's#\]\(idea-card\.md#](Idea-Card#g'
}

count=0
echo "$PAGES" | while IFS='|' read -r src page; do
    [ -z "$src" ] && continue

    if ! git ls-files --error-unmatch "$src" >/dev/null 2>&1; then
        echo "  пропущен (не отслеживается git): $src" >&2
        continue
    fi

    rewrite_links < "$src" > "$OUT/$page.md"
    echo "  $src -> $page.md"
    count=$((count + 1))
done

# Навигация
cat > "$OUT/_Sidebar.md" <<'SIDEBAR'
### Программа

- [[Home]]
- [[Roadmap]]
- [[Team-Skills]]

### Занятия

- [[Lesson-02]]
- [[Homework-01]]
- [[Homework-02]]

### Шаблоны

- [[Idea-Card]] (RU)
- [[Idea-Card-HY]] (HY)
- [[Idea-Card-EN]] (EN)

### Процесс

- [[Idea-Pipeline]]
- [[Telegram-Messages]]
SIDEBAR

cat > "$OUT/_Footer.md" <<'FOOTER'
---

⚠️ Эта Wiki генерируется автоматически из репозитория
[handbook](https://github.com/RealSchoolPool/handbook). Правки, сделанные прямо здесь,
будут стёрты при следующей синхронизации — меняй файлы в `docs/` через Pull Request.
FOOTER

echo "готово: $OUT"
