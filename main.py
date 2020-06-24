#!/usr/bin/env python3

import base64
import configparser
import logging
import os.path
import signal
import sys
from functools import wraps

import telegram
from deluge_client import DelugeRPCClient
from telegram.ext import MessageHandler, Filters, Updater

config = configparser.ConfigParser()
config.read('config.ini')

logging.basicConfig(level=config.get('logging', 'level', fallback='INFO'),
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

deluge_client = DelugeRPCClient(config.get('deluge', 'host'),
                                int(config.get('deluge', 'port')),
                                config.get('deluge', 'username'),
                                config.get('deluge', 'password'),
                                decode_utf8=True)
deluge_client.connect()

ALLOWED_TELEGRAM_USER_IDS = [int(x) for x in config['telegram'].get('UserIds', "").split(",")]


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


def get_deluge_torrent_name_by_id(deluge_torrent_id):
    status = deluge_client.core.get_torrents_status({'id': deluge_torrent_id}, ['name'])
    for key in status:
        return status[key]['name']


@restricted
def handle_message(update, context):
    message = update.message.text
    if isinstance(message, str) and message.startswith('magnet'):
        magnet_uri = message
        try:
            deluge_torrent_id = deluge_client.core.add_torrent_magnet(magnet_uri, {})
            torrent_name = get_deluge_torrent_name_by_id(deluge_torrent_id)
            context.bot.send_message(chat_id=update.effective_chat.id, text="Downloading `{0}`".format(torrent_name),
                                     parse_mode=telegram.ParseMode.MARKDOWN)
        except Exception as e:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Error add torrent: {}".format(str(e)))
    else:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="Link is not magnet".format(message),
                                 parse_mode=telegram.ParseMode.MARKDOWN)


@restricted
def handle_file(update, context):
    file_name = update.message.document.file_name
    root, ext = os.path.splitext(file_name)
    if ext == '.torrent':
        try:
            file_id = update.message.document.file_id
            file = context.bot.get_file(file_id)
            base64_file = base64.b64encode(file.download_as_bytearray())
            deluge_torrent_id = deluge_client.core.add_torrent_file(file_name, base64_file.decode("utf-8"), {})
            torrent_name = get_deluge_torrent_name_by_id(deluge_torrent_id)
            context.bot.send_message(chat_id=update.effective_chat.id, text="Downloading `{0}`".format(torrent_name),
                                     parse_mode=telegram.ParseMode.MARKDOWN)

        except Exception as e:
            context.bot.send_message(chat_id=get_deluge_torrent_name_by_id,
                                     text="Error add torrent file: {}".format(str(e)))
    else:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="File `{}` is not a `.torrent`".format(file_name),
                                 parse_mode=telegram.ParseMode.MARKDOWN)


# def add_magnet(update, context):
#     message = context.args[0]
#     magnet_add = deluge_client.core.add_torrent_magnet(message, {})
#     status = deluge_client.core.get_torrents_status({'id': magnet_add}, ['name'])
#     update.message.reply_text("add {}".format(status))


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
message_handler = MessageHandler(Filters.text & (~Filters.command), handle_message)
file_handler = MessageHandler(Filters.document, handle_file)
dispatcher = tg_updater.dispatcher
dispatcher.add_handler(message_handler)
dispatcher.add_handler(file_handler)
# tg_updater.dispatcher.add_handler(CommandHandler("add_magnet", add_magnet))


def stop_app(g, i):
    try:
        tg_updater.stop()
        deluge_client.disconnect()
        sys.exit(0)
    except Exception as e:
        logging.error("Exiting immediately cause error {}".format(e))
        sys.exit(1)


signal.signal(signal.SIGINT, stop_app)
signal.signal(signal.SIGTERM, stop_app)

tg_updater.start_polling()

signal.pause()
