import datetime
import os
import asyncpg
import asyncio
import aiohttp
import pytz
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()
DB_POOL: asyncpg.Pool | None = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    await update.message.reply_text(
            'Нажми на кнопку в меню ниже \n\np.s Ответ от сервера занимает до 20 секунд :('
        )
    if DB_POOL:
        try:
            async with DB_POOL.acquire() as connection:
                status = await connection.execute("""
                    INSERT INTO f1_bot (chat_id)
                    VALUES ($1)
                    ON CONFLICT (chat_id) DO NOTHING
                    """, chat_id)
                if status =='INSERT 0 1':
                    print(f'Пользователь {chat_id} добавлен в DB')
                    await update.message.reply_text(f'Ваш chat_id ={chat_id} добавлен базу данных для рассылки расписания гонок')
                else:
                    print(f'Пользователь {chat_id} уже есть в базе')
                    await update.message.reply_text('Вы уже есть в базе данных')
        except Exception as e:
            print(f'Ошибка при сохранении в DB: {e}')
            await update.message.reply_text(f'Ваш chat_id:{chat_id}, не удалось подключить к авторассылке ошибка {e}')
    else:
        await update.message.reply_text('Ошибка инициализации пула, авторассылка отключена')

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
    if DB_POOL:
        try:
            async with DB_POOL.acquire() as connection:
                status = await connection.execute("""
                UPDATE f1_bot 
                SET is_subscribe = False 
                WHERE chat_id = $1::bigint AND is_subscribe = True;                
                """,chat_id)
                if status == 'UPDATE 1':
                    await update.message.reply_text('✅ Вы успешно отписались от рассылки')
                    print(f'Пользователь {chat_id} отписался от рассылки')
                    return
                user_exists = await connection.fetchval("""
                SELECT * FROM f1_bot 
                WHERE chat_id = $1::bigint;
                """,chat_id)
                if not user_exists:
                    await update.message.reply_text('❌ Тебя нет в базе. Рассылка не была подключена')
                else:
                    await update.message.reply_text('Вы уже отписаны от рассылки')

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
                status = await connection.execute("""
                UPDATE f1_bot 
                SET is_subscribe = True 
                WHERE chat_id = $1::bigint AND is_subscribe = False;                
                """,chat_id)
                if status == 'UPDATE 1':
                    print(f'Пользователь {chat_id} подписался на рассылку')
                    await update.message.reply_text('✅ Вы успешно подписались на рассылку')
                    return
                user_exists = await connection.fetchval("""
                SELECT * FROM f1_bot 
                WHERE chat_id = $1::bigint;
                """,chat_id)
                if not user_exists:
                    await update.message.reply_text('❌ Тебя нет в базе. Нажми /start')
                else:
                    await update.message.reply_text('Вы уже подписаны на рассылку')
        except Exception as e:
            print(f'Ошибка при подписке пользователя {chat_id}: {e}')
            await update.message.reply_text(f'Произошла ошибка: {e}')
    else:
        await update.message.reply_text('Ошибка инициализации пула')

async def next_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = user.id
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
            next_race_message += f'{country}, начало в {samara_datetime.strftime("%H:%M")}'
            await update.message.reply_text(next_race_message)

async def next_qualifying(update: Update, context: ContextTypes.DEFAULT_TYPE):
    next_race_url = 'https://api.jolpi.ca/ergast/f1/current/next.json'
    next_race_message = 'Следующая квалификация:\n'
    async with aiohttp.ClientSession() as session:
        async with session.get(next_race_url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][0]
            country = table['raceName']
            time = table['Qualifying']['time']
            clean_time = time.replace('Z', '')
            date = table['Qualifying']['date']
            date_time = datetime.datetime.strptime(
                f'{date} {clean_time}', '%Y-%m-%d %H:%M:%S'
            )
            utc_datetime = pytz.utc.localize(date_time)
            samara_timezone = pytz.timezone('Europe/Samara')
            samara_datetime = utc_datetime.astimezone(samara_timezone)
            next_race_message += (
                f'{country}, начало в {samara_datetime.strftime("%H:%M")}'
            )
            await update.message.reply_text(next_race_message)

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


async def schedule_qualifying(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    schedule_url = f'https://api.jolpi.ca/ergast/f1/{datetime.date.today().year}/last/qualifying.json'
    async with aiohttp.ClientSession() as session:
        async with session.get(schedule_url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][-1]
            country = table['Circuit']['Location']['country']
            time = table['time']
            clean_time = time.replace('Z', '')
            date = table['date']
            date_time = datetime.datetime.strptime(
                f'{date} {clean_time}', '%Y-%m-%d %H:%M:%S'
            )
            utc_datetime = pytz.utc.localize(date_time)
            samara_timezone = pytz.timezone('Europe/Samara')
            samara_datetime = utc_datetime.astimezone(samara_timezone)
            schedule_message = f'{country}\n Начало квалификации: {samara_datetime.strftime("%H:%M")}\n'
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
    race_url = f'https://api.jolpi.ca/ergast/f1/{datetime.date.today().year}/last/results.json'
    async with aiohttp.ClientSession() as session:
        async with session.get(race_url) as resp:
            data = await resp.json()
            table = data['MRData']['RaceTable']['Races'][-1]
            country = table['Circuit']['Location']['country']
            time = table['time']
            clean_time = time.replace('Z', '')
            date = table['date']
            date_time = datetime.datetime.strptime(
                f'{date} {clean_time}', '%Y-%m-%d %H:%M:%S'
            )
            utc_datetime = pytz.utc.localize(date_time)
            samara_timezone = pytz.timezone('Europe/Samara')
            samara_datetime = utc_datetime.astimezone(samara_timezone)
            last_race = f'{country}\n Начало гонки: {samara_datetime.strftime("%H:%M")}\n'
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

async def create_db_pool(application):
    global DB_POOL
    db_url = os.getenv('DATABASE_URL') # Безопасное получение ключа
    if not db_url:
        print('DATABASE_URL не найден в env')
        return
    try:
        DB_POOL = await asyncpg.create_pool(
            dsn=db_url,
            min_size=2,
            max_size=3
        )
        print('Пул подключений к PostgreSQL создан!')
    except Exception as e:
        print(f'Ошибка при создании пула: {e}')





if __name__ == '__main__':
    token = os.getenv('BOT_TOKEN')
    if token is None:
        raise ValueError('Токен не найден')
    app = ApplicationBuilder().token(token).post_init(create_db_pool).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('teams', composition_of_the_team))
    app.add_handler(CommandHandler('last_qualifying', schedule_qualifying))
    app.add_handler(CommandHandler('last_race', race))
    app.add_handler(CommandHandler('next_race', next_race))
    app.add_handler(CommandHandler('next_qualifying',next_qualifying ))
    app.add_handler(CommandHandler('subscribe', subscribe))
    app.add_handler(CommandHandler('unsubscribe', unsubscribe))


    print('Бот запущен и ждет сообщений')
    app.run_polling()
