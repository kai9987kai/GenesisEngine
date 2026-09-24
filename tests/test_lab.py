import copy
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from genesis.experiments import digest, normalize_manifest, paired_statistics, run_experiment, METRICS
from genesis.server import LabServer
from genesis.simulation import Simulation


class LabTests(unittest.TestCase):
    def manifest(self):
        return {"name": "test", "seeds": [4, 9], "ticks": 8, "config": {"population": 3, "learning": "none"}, "intervention": {"learning": "none"}}

    def test_identical_arms_have_zero_effect_and_repeat(self):
        a = run_experiment(self.manifest())
        b = run_experiment(self.manifest())
        self.assertEqual(a["rows"], b["rows"])
        self.assertEqual(a["statistics"], b["statistics"])
        for estimate in a["statistics"].values():
            self.assertEqual(estimate["difference"], 0)
            self.assertEqual(estimate["ci95"], [0, 0])
        self.assertEqual(a["rows"][0]["snapshot_hash"], a["rows"][1]["snapshot_hash"])

    def test_exported_receipts_match_snapshots_and_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            result = run_experiment(self.manifest(), out)
            for name in ["manifest.json", "raw.csv", "population.csv", "lineage.json", "statistics.json", "report.md", "plots/population.svg"]:
                self.assertTrue((out / name).is_file(), name)
            for row in result["rows"]:
                snap = json.loads((out / "snapshots" / f"seed-{row['seed']}-{row['condition']}.genrun").read_text())
                self.assertEqual(digest(snap), row["snapshot_hash"])
                loaded = Simulation.from_snapshot(snap)
                original = Simulation(row["seed"], self.manifest()["config"])
                original.step(13)
                loaded.step(5)
                self.assertEqual(original.snapshot(), loaded.snapshot())

    def test_paired_bootstrap_uses_differences(self):
        rows = []
        for seed in [1, 2, 3]:
            for condition, value in [("control", seed*10), ("intervention", seed*10+2)]:
                rows.append({"seed": seed, "condition": condition, **{m: value for m in METRICS}})
        for result in paired_statistics(rows).values():
            self.assertEqual(result["difference"], 2)
            self.assertEqual(result["ci95"], [2, 2])
        with self.assertRaises(ValueError):
            paired_statistics(rows[:-1])

    def test_invalid_manifests(self):
        for change in [{"seeds": [1, 1]}, {"seeds": [True, 2]}, {"seeds": [[1], 2]}, {"ticks": -1}, {"ticks": 1.2},
                       {"conditions": ["developmental", "direct"]}, {"unknown": 1}, {"metrics": ["survival"]}]:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                normalize_manifest({**self.manifest(), **change})

    def test_developmental_treatment_changes_initial_embryos(self):
        manifest = {**self.manifest(), "ticks": 1, "intervention": {"nutrients": .3}}
        result = run_experiment(manifest)
        self.assertNotEqual(result["statistics"]["mean_cells"]["difference"], 0)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = LabServer(("127.0.0.1", 0), 5)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, data=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        req = urllib.request.Request(self.base+path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

    def test_api_snapshot_step_and_restore(self):
        self.request("/api/reset", {"seed": 5, "config": {"population": 3}})
        snapshot = self.request("/api/snapshot")
        view = self.request("/api/step", {"ticks": 4})
        self.assertEqual(view["tick"], 4)
        self.request("/api/load", {"snapshot": snapshot})
        self.assertEqual(self.request("/api/step", {"ticks": 4}), view)

    def test_rejected_import_does_not_modify_live_world(self):
        before = self.request("/api/snapshot")
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/load", {"snapshot": {"version": "bad"}})
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(before, self.request("/api/snapshot"))

    def test_cross_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/step", {"ticks": 1}, "https://example.com")
        self.assertEqual(error.exception.code, 403)

    def test_static_route_cannot_read_source(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.base+"/../src/genesis/server.py")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
