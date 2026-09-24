import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from genesis.cli import main
from genesis.simulation import Simulation


class CLITests(unittest.TestCase):
    def run_cli(self, args):
        with contextlib.redirect_stdout(io.StringIO()):
            main(args)

    def test_develop_simulate_preserves_development_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            genome, organism, snapshot, continued = [str(Path(tmp) / name) for name in
                ("genome.json", "organism.json", "run.genrun", "continued.genrun")]
            self.run_cli(["genome", "--seed", "4", "--output", genome])
            self.run_cli(["develop", genome, "--seed", "8", "--nutrients", "0.3", "--temperature", "0.8", "--output", organism])
            self.run_cli(["simulate", organism, "--ticks", "0", "--output", snapshot])
            embryo = json.loads(Path(organism).read_text())["body"]
            run = json.loads(Path(snapshot).read_text())
            self.assertEqual(run["config"]["nutrients"], .3)
            self.assertEqual(run["config"]["temperature"], .8)
            body = run["organisms"][0]["body"]
            self.assertEqual([(c["type"], c["expression"]) for c in embryo["cells"]], [(c["type"], c["expression"]) for c in body["cells"]])
            self.assertEqual(embryo["brain"], body["brain"])
            self.run_cli(["replay", snapshot, "--ticks", "3", "--output", continued])
            expected = Simulation.from_snapshot(run)
            expected.step(3)
            self.assertEqual(expected.snapshot(), json.loads(Path(continued).read_text()))

    def test_cli_tick_limit_matches_runtime(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.run_cli(["simulate", "--ticks", "10001"])
        self.assertEqual(error.exception.code, 2)
