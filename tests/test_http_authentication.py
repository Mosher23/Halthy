"""Real HA auth middleware/router tests with temporary users and loopback HTTP.

Run separately from stub tests using tests/requirements.txt and Python 3.13.
No production HA configuration, credentials or remote server is used.
"""
from datetime import datetime, timedelta, timezone
from ipaddress import ip_network
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from homeassistant import auth
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.components import webhook
from homeassistant.components.auth import RevokeTokenView, TokenView
from homeassistant.components.http import HomeAssistantHTTP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from custom_components import halthy as bridge
from custom_components.halthy.paired_webhook import (
    HalthyWebhookManager,
    HalthyWebhookPairingView,
    MANAGER_KEY,
)


class HTTPAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_rollover_and_delayed_retry_through_api_and_paired_webhook(self):
        pairing = self.pairing()
        await self.pair(pairing)
        self.hass.config.time_zone = "Europe/Berlin"
        yesterday = datetime(2026, 10, 14, 20, tzinfo=timezone.utc)
        midnight = datetime(2026, 10, 14, 22, tzinfo=timezone.utc)
        morning = datetime(2026, 10, 15, 6, tzinfo=timezone.utc)

        def clock(instant):
            class Clock(datetime):
                @classmethod
                def now(cls, tz=None):
                    return instant.astimezone(tz or timezone.utc)
            return patch.object(bridge, "datetime", Clock)

        def payload(day, value, measured, completed=False):
            attrs = {"day_start": day + "T00:00:00+02:00", "day_end": day + "T23:00:00+02:00",
                     "reporting_time_zone": "Europe/Berlin", "measurement_timestamp": measured.isoformat()}
            return {"username": "tester", "device_id": "phone", "sync_completed": completed, "sensors": [
                {"key": "steps", "state": value, "unit": "count", "attributes": attrs},
                {"key": "screen_time", "state": value, "unit": "min", "attributes": attrs},
                {"key": "first_pickup_time", "state": measured.isoformat(), "attributes": attrs}]}

        def value(key):
            return next(record.state for record in self.runtime.sensors.values() if record.metric_key == key)

        with clock(yesterday), patch.object(bridge, "_current_local_day_key", return_value="2026-10-14"):
            response = await self.client.post("/api/halthy/push", json=payload("2026-10-14", 9000, yesterday, True), headers=self.headers())
            self.assertEqual(response.status, 200, await response.text())
        last_sync = value("last_full_sync")
        with clock(midnight), patch.object(bridge, "_current_local_day_key", return_value="2026-10-15"):
            await bridge._async_reset_daily_upload_counter_for_entry(self.hass, "entry")
        self.assertEqual(value("steps"), 0)
        self.assertEqual(value("screen_time"), 0)
        self.assertEqual(value("first_pickup_time"), "unknown")
        self.assertEqual(value("daily_upload_count"), 0)
        self.assertEqual(value("last_full_sync"), last_sync)
        routes = [("/api/halthy/push", self.headers()), ("/api/webhook/" + pairing["webhook_id"], {})]
        with clock(morning), patch.object(bridge, "_current_local_day_key", return_value="2026-10-15"):
            for path, headers in routes:
                response = await self.client.post(path, json=payload("2026-10-14", 9999, yesterday), headers=headers)
                self.assertEqual(response.status, 200, await response.text())
                self.assertEqual((await response.json())["ignored_older"], 3)
                self.assertEqual(value("steps"), 0)
                self.assertEqual(value("screen_time"), 0)
            for path, headers in routes:
                response = await self.client.post(path, json=payload("2026-10-15", 10, morning, True), headers=headers)
                self.assertEqual(response.status, 200, await response.text())
                self.assertEqual(value("steps"), 10)
                self.assertEqual(value("screen_time"), 10)
            self.assertEqual(value("daily_upload_count"), 2)
            self.assertNotEqual(value("last_full_sync"), last_sync)

    async def asyncSetUp(self):
        self.directory = TemporaryDirectory(prefix="halthy-real-ha-")
        self.hass = HomeAssistant(self.directory.name)
        await entity_registry.async_load(self.hass)
        self.hass.auth = await auth.auth_manager_from_config(self.hass, [], [])
        self.owner = await self.hass.auth.async_create_user(
            "Synthetic Halthy owner", group_ids=[GROUP_ID_ADMIN]
        )
        self.other = await self.hass.auth.async_create_user(
            "Synthetic unrelated user", group_ids=[GROUP_ID_ADMIN]
        )
        self.grant = await self.new_grant(self.owner)
        self.other_grant = await self.new_grant(self.other)
        self.runtime = bridge.IntegrationRuntime(
            configured_username="tester", app_username="tester",
            display_name="Tester", owner_user_id=self.owner.id,
            statistics_enabled=False,
        )
        self.hass.data[bridge.DOMAIN] = {"entries": {"entry": self.runtime}}
        self.manager = HalthyWebhookManager(self.hass, bridge.HalthyPushView().post)
        await self.manager.load()
        self.hass.data[bridge.DOMAIN][MANAGER_KEY] = self.manager
        self.http = HomeAssistantHTTP(
            self.hass, ssl_certificate=None, ssl_peer_certificate=None, ssl_key=None,
            server_host=["127.0.0.1"], server_port=0,
            trusted_proxies=[ip_network("127.0.0.1/32")],
            ssl_profile="modern",
        )
        self.hass.http = self.http
        await self.http.async_initialize(
            cors_origins=[], use_x_forwarded_for=True, login_threshold=-1,
            is_ban_enabled=False, use_x_frame_options=True,
        )
        for view in (bridge.HalthyConnectionsView, bridge.HalthyPushView,
                     HalthyWebhookPairingView, webhook.WebhookView, RevokeTokenView):
            self.http.register_view(view)
        # Code exchange/browser approval is out of scope; this exercises refresh.
        self.http.register_view(TokenView(lambda _client, _code: None))
        self.client = TestClient(TestServer(self.http.app, host="127.0.0.1"))
        await self.client.start_server()

    async def asyncTearDown(self):
        if hasattr(self, "client"):
            await self.client.close()
        if hasattr(self, "hass"):
            await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def new_grant(self, user, **kwargs):
        return await self.hass.auth.async_create_refresh_token(
            user, client_id="https://example.invalid/halthy-test/", **kwargs
        )

    def headers(self, grant=None):
        token = self.hass.auth.async_create_access_token(grant or self.grant)
        return {"Authorization": "Bearer " + token}

    def pairing(self):
        return {
            "version": 1, "action": "pair", "registration_id": str(uuid4()),
            "entry_id": "entry", "username": "tester", "device_id": "phone",
            "webhook_id": uuid4().hex + uuid4().hex,
        }

    async def pair(self, payload):
        response = await self.client.post(
            "/api/halthy/webhook", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 200, await response.text())
        result = await response.json()
        self.assertEqual(result["registration_id"], payload["registration_id"])
        self.assertFalse(result["revoked"])
        return result

    async def test_authenticated_discovery_uses_real_account_and_hides_other_profiles(self):
        response = await self.client.get("/api/halthy/connections")
        self.assertEqual(response.status, 401)
        response = await self.client.get(
            "/api/halthy/connections", headers={"Authorization": "Bearer invalid"}
        )
        self.assertEqual(response.status, 401)
        response = await self.client.get("/api/halthy/connections", headers=self.headers())
        self.assertEqual(response.status, 200)
        result = await response.json()
        self.assertEqual(result["account_id"], self.owner.id)
        self.assertEqual(result["profiles"], [
            {"entry_id": "entry", "username": "tester", "display_name": "Tester"}
        ])
        response = await self.client.get(
            "/api/halthy/connections", headers=self.headers(self.other_grant)
        )
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["profiles"], [])

    async def test_probe_requires_auth_and_does_not_write_or_claim(self):
        payload = {"username": "tester", "device_id": "phone", "connection_test": True}
        response = await self.client.post("/api/halthy/push", json=payload)
        self.assertEqual(response.status, 401)
        response = await self.client.post(
            "/api/halthy/push", json=payload, headers=self.headers(self.other_grant)
        )
        self.assertEqual(response.status, 403)
        response = await self.client.post(
            "/api/halthy/push", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {
            "ok": True, "connection_test": True, "entry_id": "entry",
            "sync_completion_supported": True, "sync_completion_receipts": True,
        })
        self.assertEqual(self.runtime.sensors, {})
        self.assertEqual(self.runtime.owner_user_id, self.owner.id)

    async def test_pairing_gets_real_issuing_grant_and_hook_cannot_run_control(self):
        payload = self.pairing()
        response = await self.client.post("/api/halthy/webhook", json=payload)
        self.assertEqual(response.status, 401)
        response = await self.client.post(
            "/api/halthy/webhook", json=payload, headers=self.headers(self.other_grant)
        )
        self.assertEqual(response.status, 403)
        await self.pair(payload)
        record = self.manager.records[payload["registration_id"]]
        self.assertEqual(record["grant_id"], self.grant.id)
        self.assertEqual(record["owner_id"], self.owner.id)
        response = await self.client.post(
            "/api/webhook/" + payload["webhook_id"],
            json={"username": "tester", "device_id": "phone", "connection_test": True},
        )
        self.assertEqual(response.status, 403)
        self.assertEqual((await response.json())["error"], "write_scope_mismatch")

    async def test_write_hook_confirms_metric_and_rejects_wrong_device(self):
        payload = self.pairing()
        await self.pair(payload)
        sample = {
            "username": "tester", "device_id": "phone", "prune_unselected_metrics": False,
            "sensors": [{"key": "heart_rate", "state": 90, "unit": "bpm"}],
        }
        api_sample = {**sample, "sensors": [{"key": "heart_rate", "state": 89, "unit": "bpm"}]}
        response = await self.client.post(
            "/api/halthy/push", json=api_sample, headers=self.headers()
        )
        self.assertEqual(response.status, 200, await response.text())
        response = await self.client.post("/api/webhook/" + payload["webhook_id"], json=sample)
        self.assertEqual(response.status, 200, await response.text())
        result = await response.json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["accepted"], 1)
        records = [record for record in self.runtime.sensors.values() if record.metric_key == "heart_rate"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].state, 90)
        sample["device_id"] = "other-phone"
        sample["sensors"][0]["state"] = 120
        response = await self.client.post("/api/webhook/" + payload["webhook_id"], json=sample)
        self.assertEqual(response.status, 403)
        records = [record for record in self.runtime.sensors.values() if record.metric_key == "heart_rate"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].state, 90)

    async def test_revoked_grant_blocks_hook_and_old_bearer_token(self):
        payload = self.pairing()
        await self.pair(payload)
        old_headers = self.headers()
        self.hass.auth.async_remove_refresh_token(self.grant)
        response = await self.client.get("/api/halthy/connections", headers=old_headers)
        self.assertEqual(response.status, 401)
        response = await self.client.post(
            "/api/webhook/" + payload["webhook_id"],
            json={"username": "tester", "device_id": "phone", "sensors": []},
        )
        self.assertEqual(response.status, 403)
        self.assertEqual((await response.json())["error"], "grant_not_valid")

    async def test_expired_access_token_does_not_disable_valid_grant_bound_hook(self):
        self.grant = await self.new_grant(
            self.owner, access_token_expiration=timedelta(seconds=-1)
        )
        # Pair with a valid access token from this grant, then expire access only.
        self.grant.access_token_expiration = timedelta(minutes=30)
        payload = self.pairing()
        await self.pair(payload)
        # HA accepts ten seconds of JWT clock skew.
        self.grant.access_token_expiration = timedelta(seconds=-60)
        response = await self.client.get("/api/halthy/connections", headers=self.headers())
        self.assertEqual(response.status, 401)
        response = await self.client.post(
            "/api/webhook/" + payload["webhook_id"],
            json={"username": "tester", "device_id": "phone", "sensors": [
                {"key": "heart_rate", "state": 90, "unit": "bpm"}
            ]},
        )
        self.assertEqual(response.status, 200, await response.text())
        self.assertTrue((await response.json())["ok"])

    async def test_reloaded_pairing_uses_disk_journal_and_new_grant_can_revoke_exact_id(self):
        payload = self.pairing()
        await self.pair(payload)
        async with self.manager.lock:
            self.manager.suspend_entry("entry")
        self.manager = HalthyWebhookManager(self.hass, bridge.HalthyPushView().post)
        await self.manager.load()
        async with self.manager.lock:
            self.manager.restore_entry("entry")
        self.hass.data[bridge.DOMAIN][MANAGER_KEY] = self.manager
        response = await self.client.post(
            "/api/webhook/" + payload["webhook_id"],
            json={"username": "tester", "device_id": "phone", "sensors": [
                {"key": "heart_rate", "state": 90, "unit": "bpm"}
            ]},
        )
        self.assertEqual(response.status, 200, await response.text())
        renewal = await self.new_grant(self.owner)
        revoke = {key: value for key, value in payload.items() if key != "webhook_id"}
        revoke["action"] = "revoke"
        for _ in range(2):
            response = await self.client.post(
                "/api/halthy/webhook", json=revoke, headers=self.headers(renewal)
            )
            self.assertEqual(response.status, 200, await response.text())
            self.assertTrue((await response.json())["revoked"])
        self.assertTrue(self.manager.records[payload["registration_id"]]["revoked"])
        self.assertNotIn(payload["webhook_id"], self.manager.registered)

    async def test_real_refresh_and_revoke_endpoints_preserve_then_remove_grant(self):
        request = {
            "grant_type": "refresh_token", "client_id": self.grant.client_id,
            "refresh_token": self.grant.token,
        }
        response = await self.client.post("/auth/token", data={**request, "client_id": "https://other.invalid/"})
        self.assertEqual(response.status, 400)
        response = await self.client.post("/auth/token", data=request)
        self.assertEqual(response.status, 200, await response.text())
        result = await response.json()
        self.assertEqual(result["token_type"], "Bearer")
        self.assertGreater(result["expires_in"], 0)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        headers = {"Authorization": "Bearer " + result["access_token"]}
        response = await self.client.get("/api/halthy/connections", headers=headers)
        self.assertEqual(response.status, 200)
        for _ in range(2):
            response = await self.client.post("/auth/revoke", data={"token": self.grant.token})
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.text(), "")
        response = await self.client.get("/api/halthy/connections", headers=headers)
        self.assertEqual(response.status, 401)
        response = await self.client.post("/auth/token", data=request)
        self.assertEqual(response.status, 400)
        self.assertEqual((await response.json())["error"], "invalid_grant")

    async def test_other_account_cannot_revoke_owned_pairing(self):
        payload = self.pairing()
        await self.pair(payload)
        revoke = {key: value for key, value in payload.items() if key != "webhook_id"}
        revoke["action"] = "revoke"
        response = await self.client.post(
            "/api/halthy/webhook", json=revoke, headers=self.headers(self.other_grant)
        )
        self.assertEqual(response.status, 403)
        self.assertFalse(self.manager.records[payload["registration_id"]]["revoked"])

    async def test_inactive_user_and_expired_pairing_cannot_write(self):
        payload = self.pairing()
        await self.pair(payload)
        sample = {"username": "tester", "device_id": "phone", "sensors": [
            {"key": "heart_rate", "state": 90, "unit": "bpm"}
        ]}
        self.owner.is_active = False
        response = await self.client.post("/api/webhook/" + payload["webhook_id"], json=sample)
        self.assertEqual(response.status, 403)
        self.assertEqual((await response.json())["error"], "grant_not_valid")
        self.owner.is_active = True
        expiration = self.manager.records[payload["registration_id"]]["expires_at"]
        self.manager.now = lambda: expiration + 1
        response = await self.client.post("/api/webhook/" + payload["webhook_id"], json=sample)
        self.assertEqual(response.status, 403)
        self.assertEqual((await response.json())["error"], "pairing_not_active")
        self.assertEqual(self.runtime.sensors, {})

    async def test_authenticated_pairing_lookup_is_read_only_exact_scope_and_secret_free(self):
        payload = self.pairing()
        await self.pair(payload)
        lookup = {key: value for key, value in payload.items() if key not in ("registration_id", "webhook_id")}
        lookup["action"] = "lookup"
        for headers, expected in (({}, 401), (self.headers(self.other_grant), 403)):
            response = await self.client.post("/api/halthy/webhook", json=lookup, headers=headers)
            self.assertEqual(response.status, expected)
            self.assertNotIn(payload["registration_id"], await response.text())
        response = await self.client.post("/api/halthy/webhook", json=lookup, headers=self.headers())
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        result = await response.json()
        self.assertEqual(result, {"ok": True, "version": 1, "account_id": self.owner.id,
            "entry_id": "entry", "username": "tester", "device_id": "phone", "pairings": [
                {"registration_id": payload["registration_id"],
                 "expires_at": self.manager.records[payload["registration_id"]]["expires_at"]}]})
        self.assertNotIn(payload["webhook_id"], str(result))
        self.assertFalse(self.manager.records[payload["registration_id"]]["revoked"])
        self.assertEqual(self.runtime.sensors, {})
        response = await self.client.post("/api/halthy/webhook", json={**lookup, "device_id": "other"}, headers=self.headers())
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["pairings"], [])

    async def test_pairing_lookup_with_renewed_grant_can_find_then_explicitly_revoke_old_record(self):
        payload = self.pairing()
        await self.pair(payload)
        self.hass.auth.async_remove_refresh_token(self.grant)
        renewal = await self.new_grant(self.owner)
        lookup = {key: value for key, value in payload.items() if key not in ("registration_id", "webhook_id")}
        lookup["action"] = "lookup"
        response = await self.client.post("/api/halthy/webhook", json=lookup, headers=self.headers(renewal))
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual((await response.json())["pairings"][0]["registration_id"], payload["registration_id"])
        revoke = {key: value for key, value in payload.items() if key != "webhook_id"}
        revoke["action"] = "revoke"
        response = await self.client.post("/api/halthy/webhook", json=revoke, headers=self.headers(renewal))
        self.assertEqual(response.status, 200, await response.text())
        response = await self.client.post("/api/halthy/webhook", json=lookup, headers=self.headers(renewal))
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["pairings"], [])

    async def test_local_only_owner_is_rejected_for_forwarded_remote_address(self):
        payload = self.pairing()
        await self.pair(payload)
        headers = self.headers()
        self.owner.local_only = True
        headers["X-Forwarded-For"] = "203.0.113.10"
        response = await self.client.get("/api/halthy/connections", headers=headers)
        self.assertEqual(response.status, 401)
        sample = {"username": "tester", "device_id": "phone", "sensors": [
            {"key": "heart_rate", "state": 90, "unit": "bpm"}
        ]}
        response = await self.client.post(
            "/api/webhook/" + payload["webhook_id"], json=sample,
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        self.assertEqual(response.status, 403)
        self.assertEqual((await response.json())["error"], "grant_not_valid")
        self.assertEqual(self.runtime.sensors, {})
        response = await self.client.post("/api/webhook/" + payload["webhook_id"], json=sample)
        self.assertEqual(response.status, 200, await response.text())


if __name__ == "__main__":
    unittest.main()
