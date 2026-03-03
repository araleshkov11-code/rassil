from pyrogram import Client, enums
from asyncio import run, sleep
from datetime import datetime, timedelta
from os.path import exists
from configparser import ConfigParser

# Чтение конфигурации
config = ConfigParser()
config.read('config.ini')
api_id = config["TOKENS"]["api_id"]
api_hash = config["TOKENS"]["api_hash"]

# Файлы с прокси и игнор-списком
proxy_file = "proxies.txt"
ignore_file = "ignore_list.txt"
ignore_chats_file = "ignored_chats.txt"  # Файл для игнорирования чатов

# Функция для чтения прокси из файла
def load_proxies():
    if exists(proxy_file):
        with open(proxy_file, 'r') as f:
            proxies = [line.strip() for line in f.readlines()]
            if proxies:
                proxy = proxies[0]  # Берём первый прокси из файла
                proxy_parts = proxy.split(':')
                if len(proxy_parts) == 4:
                    proxy_config = {
                        "scheme": "http",  # Или "socks5", в зависимости от типа прокси
                        "hostname": proxy_parts[0],
                        "port": int(proxy_parts[1]),
                        "username": proxy_parts[2],
                        "password": proxy_parts[3]
                    }
                    print(f'Используется прокси: {proxy_config}')  # Лог прокси для проверки
                    return proxy_config
    print("Прокси не найдены или файл пуст.")
    return None

# Функция для чтения игнор-списка
def load_ignore_list():
    if exists(ignore_file):
        with open(ignore_file, 'r') as f:
            return set(line.strip() for line in f.readlines())
    return set()

# Функция для чтения игнорируемых чатов
def load_ignored_chats():
    if exists(ignore_chats_file):
        with open(ignore_chats_file, 'r') as f:
            return set(line.strip() for line in f.readlines())
    return set()

# Функция для обновления игнор-списка пользователей
def update_ignore_list(ignored_users):
    with open(ignore_file, 'a') as f:
        for user in ignored_users:
            f.write(f'{user}\n')

# Функция для обновления игнор-списка чатов
def update_ignore_chats(chat):
    with open(ignore_chats_file, 'a') as f:
        f.write(f'{chat}\n')

def params():
    while True:
        try:
            time_s = int(input('Введите время ожидания между отправкой сообщений (в секундах): '))
            time_circle = int(input('Введите время ожидания между циклами (в минутах): ')) * 60
            return time_s, time_circle
        except ValueError:
            input('Вы ввели неверные данные, попробуйте снова.\n')

def mention_users():
    while True:
        answer = input('Нужно упоминать пользователей? (y/n): ').strip().lower()
        if answer in ['y', 'n']:
            return answer == 'y'
        else:
            print('Пожалуйста, введите "y" или "n".')

async def spam_chats():
    time_s, time_circle = params()
    mention = mention_users()

    # Загрузка игнор-списков
    ignored_users = load_ignore_list()
    ignored_chats = load_ignored_chats()  # Загружаем игнорируемые чаты

    # Загрузка прокси
    proxy_config = load_proxies()

    # Проверка, что прокси загружены
    if proxy_config:
        print(f"Подключение с использованием прокси: {proxy_config['hostname']}:{proxy_config['port']}")
    else:
        print("Подключение без использования прокси.")

    # Использование прокси при создании клиента Pyrogram
    async with Client('account', api_id, api_hash, proxy=proxy_config) as app:
        async for msg in app.get_chat_history("me"):
            try:
                photo_id = msg.photo.file_id
                text = msg.caption
                is_photo = True
            except AttributeError:
                text = msg.text
                is_photo = False
            break

        chats_ids = []
        async for dialog in app.get_dialogs():
            if str(dialog.chat.type) in ['ChatType.SUPERGROUP', 'ChatType.GROUP']:
                if dialog.chat.username and '@' + dialog.chat.username not in ignored_chats:  # Проверка чатов
                    chats_ids.append('@' + dialog.chat.username)
                    print(f'Нашли чат: {dialog.chat.username}')
        print(f'Кол-во найденных чатов: {len(chats_ids)}')

        while True:
            count_send_messages = 0
            for chat in chats_ids:
                chat_username = chat.replace('https://t.me/', '@')
                n = 0
                users = []
                try:
                    async for member in app.get_chat_members(chat_username, filter=enums.ChatMembersFilter.SEARCH):
                        if member.user.username and '@' + member.user.username not in ignored_users:
                            users.append('@' + member.user.username)
                            n += 1
                        if n == 6:
                            break
                except KeyError as e:
                    print(f'Пропускаем чат {chat_username} из-за ошибки KeyError: {e}')
                    continue
                except Exception as e:
                    print(f'Пропускаем чат {chat_username} из-за непредвиденной ошибки: {e}')
                    continue

                if not users:
                    print(f'Нет новых пользователей для отметки в чате {chat_username}')
                    update_ignore_chats(chat_username)  # Добавляем чат в игнор-список
                    continue

                user_str = ' '.join(users) if mention else ''
                new_text = f'{text} {user_str}'.strip()

                try:
                    if is_photo:
                        message = await app.send_photo(chat_username, photo_id, new_text)
                        if mention:
                            await app.edit_message_caption(chat_username, message.id, caption=text)
                        print(f'Отправили фото в чат - {chat_username}')
                    else:
                        message = await app.send_message(chat_username, new_text)
                        if mention:
                            await app.edit_message_text(chat_username, message.id, text=text)
                        print(f'Отправили текст в чат - {chat_username}')
                    
                    # Обновление игнор-списка пользователей
                    update_ignore_list(users)
                    ignored_users.update(users)
                    
                    count_send_messages += 1
                except Exception as _ex:
                    print(f'Не получилось отправить сообщение в чат - {chat_username}\nОшибка: {_ex}')

                await sleep(time_s)

            next_iter = datetime.now() + timedelta(minutes=time_circle / 60)
            next_iter_time = next_iter.strftime('%H:%M:%S')
            print(f'Всего отправлено сообщений: {count_send_messages}')
            print(f'Цикл закончился!\nСледующий цикл начнется в {next_iter_time}')
            await sleep(time_circle)

def main():
    print("Подписывайся на мой канал @motivation_dengy")  
    run(spam_chats())

if __name__ == '__main__':
    main()
