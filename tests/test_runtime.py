import configparser
import ssl
import unittest
from unittest.mock import patch

import certifi
from telegram.ext import Updater
from telegram.utils.request import Request

import cron_jobs
import schedule_thread
from deluge_service import DelugeService


class RuntimeTests(unittest.TestCase):
    def test_telegram_uses_corrected_ca_bundle(self):
        request = Request()
        self.assertEqual(request._con_pool.connection_pool_kw["ca_certs"], certifi.where())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(certifi.where())
        names = {
            value
            for cert in context.get_ca_certs()
            for rdn in cert["subject"]
            for key, value in rdn
            if key == "commonName"
        }
        self.assertTrue(names)
        self.assertNotIn("emSign ECC Root CA - G3", names)

    def test_legacy_telegram_updater_initializes_offline(self):
        updater = Updater("123456:offline-test-token", use_context=True)
        self.assertIsNotNone(updater.dispatcher)
        self.assertIsNotNone(updater.job_queue)

    @patch("deluge_service.DelugeRPCClient")
    def test_deluge_label_configuration_and_magnet_forwarding(self, client_type):
        config = configparser.ConfigParser()
        config["deluge"] = {
            "host": "example.invalid", "port": "58846", "username": "test",
            "password": "test", "LabelEnable": "true", "LabelId": "telegram",
        }
        client = client_type.return_value
        client.core.add_torrent_magnet.return_value = "torrent-id"
        service = DelugeService(config)
        self.assertEqual(service.add_torrent_magnet("magnet:?xt=test"), "torrent-id")
        client.core.add_torrent_magnet.assert_called_once_with("magnet:?xt=test", {})
        client.label.set_torrent.assert_called_once_with("torrent-id", "telegram")


if __name__ == "__main__":
    unittest.main()
