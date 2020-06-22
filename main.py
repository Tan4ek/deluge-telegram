#!/usr/bin/env python3

import configparser
import logging
import signal
import sys

import telegram
from deluge_client import DelugeRPCClient
from telegram.ext import MessageHandler, Filters
from telegram.ext import Updater, CommandHandler

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


def handle_message(update, context):
    message = update.message.text
    if isinstance(message, str) and message.startswith('magnet'):
        magnet_uri = message
        try:
            magnet_add = deluge_client.core.add_torrent_magnet(magnet_uri, {})

            print(magnet_add)
            status = deluge_client.core.get_torrents_status({'id': magnet_add}, ['name'])
            torrent_name = ""
            for key in status:
                torrent_name = status[key]['name']
            context.bot.send_message(chat_id=update.effective_chat.id, text="Downloading `{0}`".format(torrent_name),
                                     parse_mode=telegram.ParseMode.MARKDOWN)
        except Exception as e:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Error add torrent: {}".format(str(e)))
    else:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="Link is not magnet".format(message),
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
echo_handler = MessageHandler(Filters.text & (~Filters.command), handle_message)
dispatcher = tg_updater.dispatcher
dispatcher.add_handler(echo_handler)
# tg_updater.dispatcher.add_handler(CommandHandler("add_magnet", add_magnet))


def stop_app():
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
