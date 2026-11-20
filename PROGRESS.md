# Adrobot: прогресс

- [x] 0. Репозиторий, окружение, структура
- [x] 1. Конфиг и .env
- [x] 2. KeitaroClient: первый запрос
- [x] 3. Изучить API Keitaro
- [ ] 4. Создание кампании
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
