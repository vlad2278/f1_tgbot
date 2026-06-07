import asyncio
import datetime
import os

import aiohttp
import asyncpg
import pytz
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()
DB_POOL: asyncpg.Pool | None = None
WEEKDAYS = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    await update.message.reply_text(
        'Нажми на кнопку в меню ниже \n\np.s Ответ от сервера занимает до 20 секунд :('
    )
    if DB_POOL:
        try:
            async with DB_POOL.acquire() as connection:
                status = await connection.execute(
                    """
                    INSERT INTO f1_bot (chat_id)
                    VALUES ($1)
                    ON CONFLICT (chat_id) DO NOTHING
                    """,
                    chat_id,
                )
                if status == 'INSERT 0 1':
                    print(f'Пользователь {chat_id} добавлен в DB')
                    await update.message.reply_text(
                        f'Ваш chat_id ={chat_id} добавлен базу данных для рассылки расписания гонок'
                    )
                else:
                    print(f'Пользователь {chat_id} уже есть в базе')
                    await update.message.reply_text(
                        'Вы уже есть в базе данных'
                    )
        except Exception as e:
            print(f'Ошибка при сохранении в DB: {e}')
            await update.message.reply_text(
                f'Ваш chat_id:{chat_id}, не удалось подключить к авторассылке ошибка {e}'
            )
    else:
        await update.message.reply_text(
            'Ошибка инициализации пула, авторассылка отключена'
        )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    if DB_POOL:
        try:
            async with DB_POOL.acquire() as connection:
                status = await connection.execute(
                    """
                UPDATE f1_bot 
                SET is_subscribe = False 
                WHERE chat_id = $1::bigint AND is_subscribe = True;                
                """,
                    chat_id,
                )
                if status == 'UPDATE 1':
                    await update.message.reply_text(
                        '✅ Вы успешно отписались от рассылки'
                    )
                    print(f'Пользователь {chat_id} отписался от рассылки')
                    return
                user_exists = await connection.fetchval(
                    """
                SELECT * FROM f1_bot 
                WHERE chat_id = $1::bigint;
                """,
                    chat_id,
                )
                if not user_exists:
                    await update.message.reply_text(
                        '❌ Тебя нет в базе. Рассылка не была подключена'
                    )
                else:
                    await update.message.reply_text(
                        'Вы уже отписаны от рассылки'
                    )

        except Exception as e:
            print(f'Ошибка при отписке пользователя {chat_id}: {e}')
            await update.message.reply_text(f'Произошла ошибка: {e}')
    else:
        await update.message.reply_text('Ошибка инициализации пула')


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    if DB_POOL:
        try:
            async with DB_POOL.acquire() as connection:
                status = await connection.execute(
                    """
                UPDATE f1_bot 
                SET is_subscribe = True 
                WHERE chat_id = $1::bigint AND is_subscribe = False;                
                """,
                    chat_id,
                )
                if status == 'UPDATE 1':
                    print(f'Пользователь {chat_id} подписался на рассылку')
                    await update.message.reply_text(
                        '✅ Вы успешно подписались на рассылку'
                    )
                    return
                user_exists = await connection.fetchval(
                    """
                SELECT * FROM f1_bot 
                WHERE chat_id = $1::bigint;
                """,
                    chat_id,
                )
                if not user_exists:
                    await update.message.reply_text(
                        '❌ Тебя нет в базе. Нажми /start'
                    )
                else:
                    await update.message.reply_text(
                        'Вы уже подписаны на рассылку'
                    )
        except Exception as e:
            print(f'Ошибка при подписке пользователя {chat_id}: {e}')
            await update.message.reply_text(f'Произошла ошибка: {e}')
    else:
        await update.message.reply_text('Ошибка инициализации пула')


async def next_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = await get_next_race_text()
    await update.message.reply_text(text)


async def next_qualifying(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = await get_next_qualifying_text()
    await update.message.reply_text(text)


async def composition_of_the_team(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    composition_url = f'https://api.jolpi.ca/ergast/f1/{datetime.date.today().year}/driverstandings.json'
    composition_message = 'Текущий зачет:\n'
    async with aiohttp.ClientSession() as session:
        async with session.get(composition_url) as resp:
            data = await resp.json()
            table = data['MRData']['StandingsTable']['StandingsLists'][0][
                'DriverStandings'
            ]
            for pilot in table:
                pilot_name = pilot['Driver']['familyName']
                team_name = pilot['Constructors'][0]['name']
                score = pilot['points']
                composition_message += f'{team_name}: {pilot_name} {score}\n'
            await update.message.reply_text(composition_message)


async def schedule_qualifying(update: Update, context: ContextTypes.DEFAULT_TYPE):
    round_num = await get_latest_qualifying_round()
    schedule_url = (
        f'https://api.jolpi.ca/ergast/f1/current/{round_num}/qualifying.json'
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(schedule_url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][0]
            raceName = table['raceName']
            time = table['time']
            clean_time = time.replace('Z', '')
            date = table['date']
            date_time = datetime.datetime.strptime(
                f'{date} {clean_time}', '%Y-%m-%d %H:%M:%S'
            )
            utc_datetime = pytz.utc.localize(date_time)
            samara_timezone = pytz.timezone('Europe/Samara')
            samara_datetime = utc_datetime.astimezone(samara_timezone)
            day_name = WEEKDAYS[samara_datetime.weekday()]
            schedule_message = f'{raceName}\n Начало квалификации: {day_name} {samara_datetime.strftime("%d-%m %H:%M")}\n'
            for pilot in table['QualifyingResults']:
                name = pilot['Driver']['familyName']
                team_name = pilot['Constructor']['name']
                position = pilot['position']
                result = pilot.get(
                    'Q3', pilot.get('Q2', pilot.get('Q1', 'Нет данных'))
                )
                schedule_message += (
                    f'{position}. {team_name} {name}: {result}\n'
                )
            await update.message.reply_text(schedule_message)


async def race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    race_url = 'https://api.jolpi.ca/ergast/f1/current/last/results.json'
    async with aiohttp.ClientSession() as session:
        async with session.get(race_url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][0]
            raceName = table['raceName']
            time = table['time']
            clean_time = time.replace('Z', '')
            date = table['date']
            date_time = datetime.datetime.strptime(
                f'{date} {clean_time}', '%Y-%m-%d %H:%M:%S'
            )
            utc_datetime = pytz.utc.localize(date_time)
            samara_timezone = pytz.timezone('Europe/Samara')
            samara_datetime = utc_datetime.astimezone(samara_timezone)
            day_name = WEEKDAYS[samara_datetime.weekday()]
            last_race = f'{raceName}\n Начало гонки: {day_name} {samara_datetime.strftime("%d-%m %H:%M")}\n'
            status_position = {
                'R': 'Сошел с дистанции (авария, поломка двигателя и т.д.)',
                'D': 'Дисквалифицирован',
                'E': 'Исключен',
                'W': 'Снялся',
                'F': 'Не квалиф.',
                'N': 'Не классиф.',
            }
            for pilot in table['Results']:
                name = pilot['Driver']['familyName']
                team_name = pilot['Constructor']['name']
                raw_position = pilot['positionText']
                position = status_position.get(raw_position, raw_position)
                last_race += f'{position}. {team_name} {name}\n'
            await update.message.reply_text(last_race)


async def post_init_setup(application):
    global DB_POOL
    db_url = os.getenv('DATABASE_URL')  # Безопасное получение ключа
    if not db_url:
        print('DATABASE_URL не найден в env')
        return
    for attempt in range(5):
        try:
            DB_POOL = await asyncpg.create_pool(dsn=db_url, min_size=2, max_size=3)
            print('Пул подключений к PostgreSQL создан!')
            break
        except Exception as e:
            print(f'База еще не готова (попытка {attempt + 1}/5). Ошибка: {e}')
            await asyncio.sleep(3)
    if not DB_POOL:
        print('Не удалось подключиться к бд')
        return
    application.job_queue.run_once(dynamic_auto_mailing_text, when=1)


async def auto_mailing_sql(context: ContextTypes.DEFAULT_TYPE):
    if not DB_POOL:
        print('Ошибка инициализации пула')
        return
    try:
        async with DB_POOL.acquire() as conn:
            subscribers = await conn.fetch("""
               SELECT chat_id
               FROM f1_bot
               WHERE is_subscribe = True 
            """)
        if not subscribers:
            return
        messages = f'{await get_next_qualifying_text()}\n\n{await get_next_race_text()} '
        for subscriber in subscribers:
            chat_id = subscriber['chat_id']
            try:
                await context.bot.send_message(chat_id=chat_id, text=messages)
                await asyncio.sleep(1)
            except Exception as e:
                print(f'Не удалось отправить {chat_id}: {e}')
    except Exception as e:
        print(f'Ошибка в рассылке: {e}')


async def get_next_race_text():
    next_race_url = 'https://api.jolpi.ca/ergast/f1/current/next.json'
    next_race_message = 'Следующая гонка:\n'
    async with aiohttp.ClientSession() as session:
        async with session.get(next_race_url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][0]
            country = table['raceName']
            time = table['time']
            clean_time = time.replace('Z', '')
            date = table['date']
            date_time = datetime.datetime.strptime(
                f'{date} {clean_time}', '%Y-%m-%d %H:%M:%S'
            )
            utc_datetime = pytz.utc.localize(date_time)
            samara_timezone = pytz.timezone('Europe/Samara')
            samara_datetime = utc_datetime.astimezone(samara_timezone)
            day_name = WEEKDAYS[samara_datetime.weekday()]
            next_race_message += f'{country}, начало в {day_name} {samara_datetime.strftime("%d-%m %H:%M")}'
            return next_race_message


async def get_next_qualifying_text():
    next_race_url = 'https://api.jolpi.ca/ergast/f1/current/next.json'
    next_race_message = 'Следующая квалификация:\n'
    async with aiohttp.ClientSession() as session:
        async with session.get(next_race_url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][0]

            # Проверяем, не прошла ли уже квалификация этого раунда
            qual_date = f'{table["Qualifying"]["date"]} {table["Qualifying"]["time"].replace("Z", "")}'
            qual_dt = pytz.utc.localize(
                datetime.datetime.strptime(qual_date, '%Y-%m-%d %H:%M:%S')
            )
            now_utc = datetime.datetime.now(pytz.utc)

            if qual_dt < now_utc:
                # Квалификация уже была — берём следующий раунд
                round_num = int(table['round']) + 1
                url2 = f'https://api.jolpi.ca/ergast/f1/current/{round_num}.json'
                async with session.get(url2) as resp2:
                    data2 = await resp2.json()
                    table = data2['MRData']['RaceTable']['Races'][0]
            country = table['raceName']
            clean_time = table['Qualifying']['time'].replace('Z', '')
            date = table['Qualifying']['date']
            date_time = datetime.datetime.strptime(f'{date} {clean_time}', '%Y-%m-%d %H:%M:%S')
            utc_datetime = pytz.utc.localize(date_time)
            samara_timezone = pytz.timezone('Europe/Samara')
            samara_datetime = utc_datetime.astimezone(samara_timezone)
            day_name = WEEKDAYS[samara_datetime.weekday()]
            next_race_message += f'{country}, начало в {day_name} {samara_datetime.strftime("%d-%m %H:%M")}'
            return next_race_message


async def get_event_datetime():
    url = 'https://api.jolpi.ca/ergast/f1/current/next.json'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][0]
            samara_timezone = pytz.timezone('Europe/Samara')
            race_date = f'{table["date"]} {table["time"].replace("Z", "")}'
            race_dt = pytz.utc.localize(
                datetime.datetime.strptime(race_date, '%Y-%m-%d %H:%M:%S')
            ).astimezone(samara_timezone)
            qual_date = f'{table["Qualifying"]["date"]} {table["Qualifying"]["time"].replace("Z", "")}'
            qual_dt = pytz.utc.localize(
                datetime.datetime.strptime(qual_date, '%Y-%m-%d %H:%M:%S')
            ).astimezone(samara_timezone)
            return race_dt, qual_dt


async def dynamic_auto_mailing_sql(context: ContextTypes.DEFAULT_TYPE):
    if not DB_POOL:
        return
    text = context.job.data
    try:
        async with DB_POOL.acquire() as conn:
            subscribers = await conn.fetch("""
            SELECT chat_id
               FROM f1_bot
               WHERE is_subscribe = True 
            """)
        for subscriber in subscribers:
            chat_id = subscriber['chat_id']
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
                await asyncio.sleep(1)
            except Exception as e:
                print(f'Не удалось отправить {chat_id}: {e}')
    except Exception as e:
        print(f'Ошибка в динамич рассылке: {e}')


async def dynamic_auto_mailing_text(context: ContextTypes.DEFAULT_TYPE):
    race_dt, qual_dt = await get_event_datetime()
    now = datetime.datetime.now(pytz.timezone('Europe/Samara'))
    grand_pri = [(qual_dt, 'Квалификация'), (race_dt, 'Гонка')]
    for event_dt, name in grand_pri:
        alert_1h = event_dt - datetime.timedelta(hours=1)
        if alert_1h > now:
            context.job_queue.run_once(
                dynamic_auto_mailing_sql,
                when=alert_1h,
                data=f'{name} начнется через 1 час',
            )
        alert_15m = event_dt - datetime.timedelta(minutes=15)
        if alert_15m > now:
            context.job_queue.run_once(
                dynamic_auto_mailing_sql,
                when=alert_15m,
                data=f'{name} начнется через 15 минут',
            )

async def get_latest_qualifying_round() -> int:
    url = 'https://api.jolpi.ca/ergast/f1/current/next.json'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][0]
            round_num = int(table['round'])

            qual_date = (
                f'{table["Qualifying"]["date"]} '
                f'{table["Qualifying"]["time"].replace("Z", "")}'
            )
            qual_dt = pytz.utc.localize(
                datetime.datetime.strptime(qual_date, '%Y-%m-%d %H:%M:%S')
            )
            now_utc = datetime.datetime.now(pytz.utc)

            # Если квалификация этого раунда уже прошла — берём его,
            # иначе берём предыдущий раунд
            return round_num if qual_dt < now_utc else round_num - 1


if __name__ == '__main__':
    token = os.getenv('BOT_TOKEN')
    if token is None:
        raise ValueError('Токен не найден')
    app = ApplicationBuilder().token(token).post_init(post_init_setup).build()
    time_zone = pytz.timezone('Europe/Samara')
    mailing_time = datetime.time(hour=12, minute=0, tzinfo=time_zone)
    app.job_queue.run_daily(auto_mailing_sql, time=mailing_time, days=(3,))
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('teams', composition_of_the_team))
    app.add_handler(CommandHandler('last_qualifying', schedule_qualifying))
    app.add_handler(CommandHandler('last_race', race))
    app.add_handler(CommandHandler('next_race', next_race))
    app.add_handler(CommandHandler('next_qualifying', next_qualifying))
    app.add_handler(CommandHandler('subscribe', subscribe))
    app.add_handler(CommandHandler('unsubscribe', unsubscribe))

    print('Бот запущен и ждет сообщений')
    app.run_polling()
