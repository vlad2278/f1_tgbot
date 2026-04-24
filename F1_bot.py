import datetime
import os

import aiohttp
import pytz
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Нажми на кнопку в меню ниже \n\np.s Ответ от сервера занимает до 20 секунд :('
    )


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


if __name__ == '__main__':
    token = os.getenv('BOT_TOKEN')
    if token is None:
        raise ValueError('Токен не найден')
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('teams', composition_of_the_team))
    app.add_handler(CommandHandler('last_qualifying', schedule_qualifying))
    app.add_handler(CommandHandler('last_race', race))
    print('Бот запущен и ждет сообщений')
    app.run_polling()
