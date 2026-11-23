# Adrobot: прогресс

- [x] 0. Репозиторий, окружение, структура
- [x] 1. Конфиг и .env
- [x] 2. KeitaroClient: первый запрос
- [x] 3. Изучить API Keitaro
- [x] 4. Создание кампании/ Если ввести данные и нажать «Создать», пока придёт ошибка 502 с 403 от Keitaro. Это ожидаемо, форма при этом работает правильно и покажет красное сообщение
- [ ] 5. Модели + Alembic
- [ ] 6. Сервис весов + тесты
- [ ] 7. Fetch streams
- [ ] 8. Add / Remove / Bring back / Pin / Cancel
- [ ] 9. Push to Keitaro
- [ ] 10. Поиск оффера
- [ ] 11. Фронт редактора
- [ ] 12. README

Стек: FastAPI + SQLAlchemy 2 + Alembic + SQLite + httpx


## Заметки по Keitaro API
- Base: {KEITARO_URL}/admin_api/v1, заголовок `Api-Key`
- Справочники: /domains (1813), /traffic_sources (836), /groups?type=campaigns (10332 FORTESTS), /offers (18813)
- Потоки кампании: GET /campaigns/{id}/streams
- Поток-редирект: type=forced, schema=redirect, action_type=http, action_payload=URL, filters=[{name: country, mode: accept, payload: [XX]}]
- Поток-офферы: type=regular, schema=landings, offers=[{offer_id, share, state}]; share = вес в %
- Создание: POST /campaigns, POST /streams
- POST /campaigns: обязательны name, alias (8 случайных символов), type=position, domain_id, group_id, traffic_source_id
- Кампания создалась: id 216857, домен kylovoa.com, группа FORTESTS. Алиас и остальные обязательные поля Keitaro подставил сам (cost_type, uniqueness_method и т. д.), так что минимальный набор полей для POST /campaigns у нас теперь известен:name, alias, type, domain_id, group_id, traffic_source_id (+ state)
- POST /streams принимает offers сразу при создании потока