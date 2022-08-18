#!/usr/bin/env python3

import base64
import configparser
import json
import logging
import os.path
import re
import signal
import sys
from datetime import datetime
from functools import wraps
from hashlib import sha256

import humanize
from emoji import emojize
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ParseMode
from telegram.ext import CallbackQueryHandler, CallbackContext, MessageHandler, Filters, Updater, CommandHandler

from cron_jobs import DeleteExpiredCacheJob, NotDownloadedTorrentsStatusCheckJob, ScanCommonTorrents
from deluge_service import DelugeService
from repository import Repository, TorrentStatus
from schedule_thread import ScheduleThread

config = configparser.ConfigParser()
config.read('config.ini')
_DB_SQLITE_FILE = 'db.sqlite3'

logging.basicConfig(level=config.get('logging', 'level', fallback='INFO'),
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

deluge_service = DelugeService(config)

repository = Repository(_DB_SQLITE_FILE)

ALLOWED_TELEGRAM_USER_IDS = [int(x) for x in config['telegram'].get('UserIds', "").split(",")]
LIST_TORRENT_SIZE = 5

EMOJI_MAP = {
    TorrentStatus.CREATED: emojize(':arrow_down:', use_aliases=True),
    TorrentStatus.DOWNLOADED: emojize(':white_check_mark:', use_aliases=True),
    TorrentStatus.DOWNLOADING: emojize(':arrow_double_down:', use_aliases=True),
    TorrentStatus.QUEUED: emojize(':back:', use_aliases=True),
    TorrentStatus.MOVING: emojize(':soon:', use_aliases=True),
    TorrentStatus.ERROR: emojize(':sos:', use_aliases=True),
    TorrentStatus.UNKNOWN_STUB: emojize(':question:', use_aliases=True)
}


def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_TELEGRAM_USER_IDS:
            logging.warning("Unauthorized access denied for {}.".format(user_id))
            context.bot.send_message(chat_id=update.effective_chat.id, text="You are not authorized")
            return
        return func(update, context, *args, **kwargs)

    return wrapped


@restricted
def handle_message(update: Update, context: CallbackContext) -> None:
    message = update.message.text
    chat_id: int = update.effective_chat.id
    user_id: int = update.effective_user.id
    if isinstance(message, str) and message.startswith('magnet'):
        magnet_uri = message
        try:
            torrent_name, deluge_torrent_id = start_download_torrent_by_magnet(magnet_uri, user_id,
                                                                               override_on_exist=True)
            context.bot.send_message(chat_id=chat_id, text="Downloading `{0}`".format(torrent_name),
                                     parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            torrent_id_matcher = torrent_id_matcher_from_exception(e)
            if type(e) and type(e).__name__ == 'AddTorrentError' and torrent_id_matcher:
                already_exist_torrent_id = torrent_id_matcher.group(1)
                cache_key = cache_key_magnet_value(already_exist_torrent_id, user_id)
                repository.create_cache(cache_key, magnet_uri, override_on_exist=True)
                reply_markup = build_reply_markup(already_exist_torrent_id, cache_key)
                context.bot.send_message(chat_id=chat_id,
                                         text='Torrent already downloaded, what to do?', reply_markup=reply_markup)
            else:
                context.bot.send_message(chat_id=chat_id, text="Error add torrent: {}".format(str(e)))
    else:
        context.bot.send_message(chat_id=chat_id,
                                 text="Link is not magnet".format(message),
                                 parse_mode=ParseMode.MARKDOWN)


@restricted
def handle_button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    try:
        cache_value = repository.get_cache(query.data)
        user_id: int = query.from_user.id
        if cache_value:
            callback_data = json.loads(cache_value['value'])
            if is_already_exist_callback(callback_data):
                torrent_id = callback_data['torrent_id']
                if callback_data['action'] == 'reload':
                    logging.debug('callback_action reload, torrent_id {}'.format(torrent_id))
                    cache_value = repository.get_cache(callback_data['cache_key'])
                    if not cache_value:
                        raise ValueError(f"no value for 'cache_key': {callback_data['cache_key']}")
                    cache_key = cache_value['key']
                    cache_value = cache_value['value']
                    if not cache_value:
                        raise ValueError(f"empty value for 'cache_key': {callback_data['cache_key']}")

                    if '_magnet_value' in cache_key and cache_value.startswith('magnet'):
                        deluge_service.delete_torrent(torrent_id)
                        torrent_name, deluge_torrent_id = start_download_torrent_by_magnet(cache_value, user_id,
                                                                                           override_on_exist=True)
                        query.edit_message_text(f'Downloading `{torrent_name}`', parse_mode=ParseMode.MARKDOWN)
                    elif '_file_value' in cache_key and len(cache_value) > 1:
                        torrent_name = deluge_service.torrent_name_by_id(torrent_id)
                        deluge_service.delete_torrent(torrent_id)
                        torrent_name, deluge_torrent_id = start_download_torrent_by_file(cache_value,
                                                                                         f'{torrent_name}.torrent',
                                                                                         user_id,
                                                                                         override_on_exist=True)
                        query.edit_message_text(f'Downloading `{torrent_name}`', parse_mode=ParseMode.MARKDOWN)
                if callback_data['action'] == 'skip':
                    logging.debug('callback_action skip, torrent_id {}'.format(torrent_id))
                    query.edit_message_text(f'Torrent `{deluge_service.torrent_name_by_id(torrent_id)}` already exist. '
                                            f'Skipping download.', parse_mode=ParseMode.MARKDOWN)
        else:
            if "next_list_" in query.data:
                offset = int(query.data.split('next_list_')[1])
                reply_markup, text = torrents_list_message(user_id, offset=offset)
                context.bot.edit_message_text(chat_id=update.effective_chat.id,
                                              message_id=update.effective_message.message_id,
                                              text=text, reply_markup=reply_markup,
                                              parse_mode=ParseMode.MARKDOWN)
            else:
                raise ValueError(f'cache is not found by key {query.data} for user {user_id} '
                                 f'({query.from_user.first_name})')
    except Exception as e:
        query.edit_message_text("Sorry, I'm broke. Try to download later.", parse_mode=ParseMode.MARKDOWN)
        logging.error('error on process callback_data {}, error: {}'.format(query.data, str(e)))


@restricted
def handle_file(update: Update, context: CallbackContext):
    file_name = update.message.document.file_name
    root, ext = os.path.splitext(file_name)
    chat_id: int = update.effective_chat.id
    user_id: int = update.effective_user.id
    if ext == '.torrent':
        file_id = update.message.document.file_id
        file = context.bot.get_file(file_id)
        base64_file_str = base64.b64encode(file.download_as_bytearray()).decode("utf-8")
        try:
            torrent_name, deluge_torrent_id = start_download_torrent_by_file(base64_file_str, file_name, user_id,
                                                                             override_on_exist=True)
            context.bot.send_message(chat_id=chat_id, text="Downloading `{0}`".format(torrent_name),
                                     parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            torrent_id_matcher = torrent_id_matcher_from_exception(e)
            if type(e) and type(e).__name__ == 'AddTorrentError' and torrent_id_matcher:
                already_exist_torrent_id = torrent_id_matcher.group(1)
                cache_key = cache_key_file_value(already_exist_torrent_id, user_id)
                repository.create_cache(cache_key, base64_file_str, override_on_exist=True)
                reply_markup = build_reply_markup(already_exist_torrent_id, cache_key)
                context.bot.send_message(chat_id=chat_id,
                                         text='Torrent already downloaded, what to do?', reply_markup=reply_markup)
            else:
                context.bot.send_message(chat_id=chat_id,
                                         text="Error add torrent file: {}".format(str(e)))
    else:
        context.bot.send_message(chat_id=chat_id,
                                 text="File `{}` is not a `.torrent`".format(file_name),
                                 parse_mode=ParseMode.MARKDOWN)


@restricted
def handle_torrents_list(update: Update, context: CallbackContext):
    chat_id: int = update.effective_chat.id
    user_id: int = update.effective_chat.id
    reply_markup, text = torrents_list_message(user_id)
    context.bot.send_message(chat_id=chat_id,
                             text=text,
                             parse_mode=ParseMode.MARKDOWN,
                             reply_markup=reply_markup)


def torrents_list_message(user_id: int, limit: int = LIST_TORRENT_SIZE, offset: int = 0):
    user_torrents = repository.all_user_torrents(user_id, limit=LIST_TORRENT_SIZE * 3, offset=offset)
    # TODO: fix not exists torrent from local db
    torrents = deluge_service.torrents_status([i['deluge_torrent_id'] for i in user_torrents])
    # last updated at the end of the list
    sorted_torrents = sorted(torrents,
                             key=lambda r: r['completed_time'] if r['completed_time'] > 0 else r['time_added'],
                             reverse=True)

    def build_message_line(t) -> str:
        progress = t.get('progress', -1.0)
        torrent_status = TorrentStatus.get_by_value_safe(t['state'])
        emoji_t = EMOJI_MAP.get(TorrentStatus.UNKNOWN_STUB)
        if torrent_status is TorrentStatus.ERROR:
            emoji_t = EMOJI_MAP.get(TorrentStatus.ERROR)
        elif progress >= 100 and torrent_status is TorrentStatus.MOVING:
            emoji_t = EMOJI_MAP.get(TorrentStatus.MOVING)
        elif progress >= 100:
            emoji_t = EMOJI_MAP.get(TorrentStatus.DOWNLOADED)
        elif progress > 0:
            emoji_t = EMOJI_MAP.get(TorrentStatus.DOWNLOADING)
        elif progress == 0:
            emoji_t = EMOJI_MAP.get(TorrentStatus.CREATED)
        if progress >= 100:
            filex_size_progress = f"{humanize.naturalsize(t['total_wanted'])} {int(progress)}%"
        else:
            filex_size_progress = f"{humanize.naturalsize(t['total_done'])} / " \
                                  f"{humanize.naturalsize(t['total_wanted'])} {int(progress)}%"
        return f"{emoji_t} **{t['name']}** \n {filex_size_progress}, added " \
               f"{humanize.naturaldate(datetime.fromtimestamp(t['time_added']))} \n"

    if offset > 0:
        if len(sorted_torrents) > LIST_TORRENT_SIZE:
            button_list = [
                InlineKeyboardButton("prev", callback_data=f"next_list_{offset - limit}"),
                InlineKeyboardButton("next", callback_data=f"next_list_{offset + limit}")
            ]
        else:
            button_list = [InlineKeyboardButton("prev", callback_data=f"next_list_{offset - limit}")]
    else:
        button_list = [InlineKeyboardButton("next", callback_data=f"next_list_{limit}")]
    reply_markup = InlineKeyboardMarkup([button_list])
    message_lines = [build_message_line(t) for t in sorted_torrents[:LIST_TORRENT_SIZE]]
    text = '\n'.join(message_lines)
    return reply_markup, text


@restricted
def handle_last_torrent_status(update: Update, context: CallbackContext):
    chat_id: int = update.effective_chat.id
    user_id: int = update.effective_chat.id
    user_torrent = repository.last_torrent(user_id)
    torrent = deluge_service.torrent_status(user_torrent['deluge_torrent_id'])

    def build_message_line(t) -> str:
        progress = t.get('progress', -1.0)
        torrent_status = TorrentStatus.get_by_value_safe(t['state'])
        emoji_t = EMOJI_MAP.get(TorrentStatus.UNKNOWN_STUB)
        if torrent_status is TorrentStatus.ERROR:
            emoji_t = EMOJI_MAP.get(TorrentStatus.ERROR)
        elif progress >= 100 and torrent_status is TorrentStatus.MOVING:
            emoji_t = EMOJI_MAP.get(TorrentStatus.MOVING)
        elif progress >= 100:
            emoji_t = EMOJI_MAP.get(TorrentStatus.DOWNLOADED)
        elif progress > 0:
            emoji_t = EMOJI_MAP.get(TorrentStatus.DOWNLOADING)
        elif progress == 0:
            emoji_t = EMOJI_MAP.get(TorrentStatus.CREATED)

        progress_message = ''
        if 0 <= progress < 100:
            progress_message = f" `{progress}%`"

        return f"{emoji_t}{progress_message} `{t['name']}`"

    context.bot.send_message(chat_id=chat_id,
                             text=build_message_line(torrent),
                             parse_mode=ParseMode.MARKDOWN)


@restricted
def handle_stop_download_torrents(update: Update, context: CallbackContext):
    chat_id: int = update.effective_chat.id
    deluge_service.stop_download_torrents()
    context.bot.send_message(chat_id=chat_id, text='Stopping download torrents', parse_mode=ParseMode.MARKDOWN)


@restricted
def handle_resume_download_torrents(update: Update, context: CallbackContext):
    deluge_service.resume_download_torrents()
    chat_id: int = update.effective_chat.id
    context.bot.send_message(chat_id=chat_id, text='Starting download torrents', parse_mode=ParseMode.MARKDOWN)


def torrent_id_matcher_from_exception(e):
    return re.search('^Torrent already in session \\((.+?)\\)\\.$', str(e), re.MULTILINE)


def sha256_str(skip_callback_data: str) -> str:
    return sha256(skip_callback_data.encode()).hexdigest()


def start_download_torrent_by_magnet(magnet_url: str, user_id: int, override_on_exist=False) -> (str, str):
    deluge_torrent_id = deluge_service.add_torrent_magnet(magnet_url)
    torrent_name = deluge_service.torrent_name_by_id(deluge_torrent_id)
    repository.create_torrent(user_id, deluge_torrent_id, override_on_exist=override_on_exist)
    return torrent_name, deluge_torrent_id


def is_already_exist_callback(callback_data: dict) -> bool:
    return callback_data['callback_data_type'] == 'already_exist_torrent'


def cache_key_magnet_value(torrent_id: str, user_id: int) -> str:
    return f'{torrent_id}_{user_id}_magnet_value'


def cache_key_file_value(torrent_id: str, user_id: int) -> str:
    return f'{torrent_id}_{user_id}_file_value'


def start_download_torrent_by_file(base64_file_str: str, file_name, user_id: int, override_on_exist=False) -> (
        str, str):
    deluge_torrent_id = deluge_service.add_torrent_file(file_name, base64_file_str)
    torrent_name = deluge_service.torrent_name_by_id(deluge_torrent_id)
    repository.create_torrent(user_id, deluge_torrent_id, override_on_exist=override_on_exist)
    return torrent_name, deluge_torrent_id


def build_reply_markup(already_exist_torrent_id, cache_key):
    # cache_key is need in case of big magnet url or big base64 of file
    skip_callback_data = json.dumps({'callback_data_type': 'already_exist_torrent', 'action': 'skip',
                                     'torrent_id': already_exist_torrent_id, 'cache_key': cache_key})
    reload_callback_data = json.dumps({'callback_data_type': 'already_exist_torrent', 'action': 'reload',
                                       'torrent_id': already_exist_torrent_id, 'cache_key': cache_key})
    # 64 bytes string, this is limit of callback_data
    skip_callback_data_hash = sha256_str(skip_callback_data)
    reload_callback_data_hash = sha256_str(reload_callback_data)
    repository.create_cache(skip_callback_data_hash, skip_callback_data, override_on_exist=True)
    repository.create_cache(reload_callback_data_hash, reload_callback_data, override_on_exist=True)
    keyboard = [
        [
            InlineKeyboardButton("Skip, do nothing", callback_data=skip_callback_data_hash),
            InlineKeyboardButton("Reload torrent", callback_data=reload_callback_data_hash)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup


def error_callback(update: Update, context: CallbackContext):
    logging.error(context.error)


tg_request_params = {}
if config.has_section('socks5'):
    socks5_cfg = config['socks5']
    tg_request_params['proxy_url'] = 'socks5://{0}:{1}'.format(socks5_cfg.get('host'), socks5_cfg.get('port'))
    if 'username' in socks5_cfg and 'password' in socks5_cfg:
        tg_request_params['urllib3_proxy_kwargs'] = {
            'username': socks5_cfg['username'],
            'password': socks5_cfg['password'],
        }

tg_updater = Updater(config.get('telegram', 'token'), use_context=True, request_kwargs=tg_request_params)
dispatcher = tg_updater.dispatcher
dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), handle_message))
dispatcher.add_handler(MessageHandler(Filters.document, handle_file))
dispatcher.add_handler(CallbackQueryHandler(handle_button_callback))
dispatcher.add_handler(CommandHandler('list', handle_torrents_list))
dispatcher.add_handler(CommandHandler('last_torrent_status', handle_last_torrent_status))
dispatcher.add_handler(CommandHandler('stop_torrents', handle_stop_download_torrents))
dispatcher.add_handler(CommandHandler('resume_torrents', handle_resume_download_torrents))
dispatcher.add_error_handler(error_callback)

st = ScheduleThread([NotDownloadedTorrentsStatusCheckJob(repository, tg_updater.bot, deluge_service),
                     ScanCommonTorrents(repository, deluge_service),
                     DeleteExpiredCacheJob(repository)])
st.start()


def stop_app(g, i):
    try:
        st.stop()
        repository.disconnect()
        tg_updater.stop()
        deluge_service.disconnect()
        sys.exit(0)
    except Exception as e:
        logging.error("Exiting immediately cause error {}".format(e))
        sys.exit(1)


signal.signal(signal.SIGINT, stop_app)
signal.signal(signal.SIGTERM, stop_app)

tg_updater.start_polling()

signal.pause()
