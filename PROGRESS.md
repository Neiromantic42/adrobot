# Adrobot: прогресс

Стек: FastAPI + SQLAlchemy 2 + Alembic + SQLite + httpx. Тесты: pytest (63 зелёных).
Репозиторий: Neiromantic42/adrobot, ветка main. Фамилия для кампаний: tananov (test_tananov_*).

## Чек-лист
- [x] 0. Репозиторий, окружение, структура
- [x] 1. Конфиг и .env
- [x] 2. KeitaroClient (get/post/put/delete)
- [x] 3. Изучение API Keitaro
- [x] 4. Создание кампании: POST /api/campaigns + форма static/index.html (проверено на эмуляторе)
- [x] 5. Модели + Alembic
- [x] 6. Сервис весов + тесты
- [x] 7. Fetch streams (слияние Keitaro и БД) + тесты, на заглушке
- [x] 8. Add / Remove / Bring back / Pin / Cancel (сервис app/services/stream_ops.py) + тесты
- [x] 9. Push to Keitaro (app/services/push.py) + тесты, формат PUT проверен на эмуляторе
- [x] 10. REST-эндпоинты редактора + поиск оффера (автокомплит)
- [x] 11. Фронт редактора (жёлтый статус потока, серые удалённые офферы, кнопки)
- [ ] 12. README (запуск, миграции, .env), публичный репозиторий, форма сдачи

## Хронология и вводные
- 17.11: получено задание. 20.11: работал со старым сервером tlgk.host.
- 23.11: tlgk.host стал отвечать 403 (Basic realm="restricted"). HR (Екатерина) подтвердила технические неполадки, продлил срок устно (прошу те же 5 дней минус выходные).
- 24.11: ТЗ обновили. Новый сервер: эмулятор Keitaro https://keitaro-for-tests.etolegko.com/admin/ (вход через GitHub). Старый tlgk.host больше не используется, его кампании (216857, 216884) неактуальны.
- Ключ API создаётся в админке: профиль, API ключи, Создать новый ключ. Хранится только в .env (в git не попадает). После сдачи удалить свой ключ.

## Эмулятор Keitaro (текущий сервер)
- Домен: 1813 (kt-emulator.test), группа кампаний: 10332 (FORTESTS), источник: 836 (FORTESTS). Дефолты лежат в app/config.py.
- Офферов 170, ID с 18001 (например, 18001 Detoxin, 18002 Fungiclean). Старый оффер 18813 не использовать.
- Тестовая кампания: id 97 (test_tananov_campaign1), поток 186 "Geo PE → Google", поток 187 "Offers" (сейчас оффер 18002 с весом 100).

## Заметки по Keitaro API (проверено)
- Base: {KEITARO_URL}/admin_api/v1, заголовок Api-Key.
- Справочники: /domains, /traffic_sources, /groups?type=campaigns (type=campaign даёт пусто), /offers.
- Потоки кампании: GET /campaigns/{id}/streams.
- Поток-редирект: type=forced, schema=redirect, action_type=http, action_payload=URL, filters=[{name: country, mode: accept, payload: [XX]}], position 1.
- Поток-офферы: type=regular, schema=landings, offers=[{offer_id, share, state}], position 2. share = вес оффера в процентах.
- POST /campaigns: обязательны name, alias (8 случайных символов), type=position, domain_id, group_id, traffic_source_id (+ state). Остальное Keitaro подставляет сам.
- POST /streams принимает offers сразу при создании потока.
- PUT /streams/{id} с {"offers": [...]} заменяет список офферов потока целиком: вес меняется, новые добавляются, оффер, которого нет в списке, удаляется (проверено на эмуляторе).
- Ошибки валидации приходят как 422 с JSON, например {"alias": ["Alias is required"]}.

## Логика редактора (из видео ТЗ)
- Состояния привязки оффера к потоку: active (есть в Keitaro), pending_add, pending_remove, removed (архив).
- Поток "жёлтый" (не опубликован), если есть pending_add, pending_remove или active-оффер, у которого weight != published_weight. Считается на лету, не хранится.
- Веса (app/services/weights.py): запиненные не меняются; остаток (100 минус сумма запиненных) делится поровну между остальными, лишние единицы по +1 первым (3 оффера: 34/33/33). pending_remove и removed получают 0.
- Крайние случаи: сумма запиненных больше 100 (WeightError); все запинены (веса не трогаем); запинено ровно 100 (свободные получают 0); единственный оффер получает 100.
- Add: новый оффер pending_add; удалённый локально (pending_remove) возвращается в active; из архива в pending_add. Remove: pending_add удаляется (привязка), active становится pending_remove с весом 0 и снятым пином. Bring back: removed в pending_add. Pin: замораживает текущий вес. Cancel: pending_add удаляются (оффер остаётся в справочнике), pending_remove возвращаются в active, веса возвращаются к published_weight.
- Push: проверяется, что сумма весов равна 100; в Keitaro уходит только active и pending_add; после успеха pending_add становятся active, pending_remove становятся removed. При ошибке Keitaro локальное состояние не меняется.
- Fetch: оффер есть в Keitaro и в базе, значит active (вес из Keitaro); пропал из Keitaro (удалён руками), значит removed; pending_add и pending_remove при fetch не затираются; потоки без офферов сохраняются просто как поток.
- published_weight (колонка stream_offers): вес, который сейчас опубликован в Keitaro; нужен для Cancel и честного жёлтого статуса.

## Не проверено / риски
- Откат при ошибке второго потока (удаление созданной кампании) не прогонялся вручную.
- Возможна ошибка 502 на форме, если Keitaro недоступен: форма показывает красное сообщение.

## Технические заметки
- Всегда запускать Alembic как python -m alembic (системный /usr/bin/alembic падает без pydantic_settings). Миграции: python -m alembic upgrade head.
- .venv лежит в ~/PycharmProjects/.venv (общий). Ставить пакеты через python -m pip, затем python -m pip freeze > requirements.txt.
- .env и *.db в .gitignore; в .env.example только заглушки.
- Миграции: 6d1d5c4dd0a1 (initial tables), b84fb2f4f641 (add published_weight).

## Ответы для формы сдачи (черновик)
- ИИ: Claude как пошаговый наставник: разбор ТЗ и видео, план, шаблоны кода и тестов, разбор ошибок. Каждый шаг запускал и проверял сам (Swagger, curl, pytest, реальные запросы к Keitaro).
- Не успел / доделал бы: заполнить после шагов 10–12.
- Перед сдачей: репозиторий публичный, в README запуск и миграции, никаких ключей и паролей в репозитории.