"""The installation of URY runs every step on its own, logs the ones that fail, and fails at the end."""

import frappe

from ury import install
from ury.setup.test_site import URYTestCase


def ok(order, name):
	def step():
		order.append(name)

	return step


class TestRunSteps(URYTestCase):
	def setUp(self):
		super().setUp()
		self.since = frappe.utils.now_datetime()
		self.addCleanup(self._remove_logs)
		self.order = []

	def _remove_logs(self):
		frappe.db.delete("Error Log", {"method": install.SETUP_ERROR, "creation": (">=", self.since)})
		frappe.db.commit()

	def steps(self, *specs):
		"""Steps made of functions of this module (the runner takes 'module:function')."""
		table = {}
		for index, (label, function) in enumerate(specs):
			name = f"step_{index}"
			table[name] = function
			setattr(_Registry, name, staticmethod(function))
		self.addCleanup(lambda: [delattr(_Registry, n) for n in table if hasattr(_Registry, n)])
		return tuple((label, f"ury.setup.test_install_steps:_Registry.{name}") for (label, _f), name in zip(specs, table))

	def logs(self):
		return frappe.get_all(
			"Error Log", filters={"method": install.SETUP_ERROR, "creation": (">=", self.since)}, fields=["error"]
		)

	def test_every_step_runs_in_order_and_nothing_is_reported(self):
		steps = self.steps(("a", ok(self.order, "a")), ("b", ok(self.order, "b")))
		self.assertEqual(install.run_steps(steps), [])
		self.assertEqual(self.order, ["a", "b"])
		self.assertEqual(self.logs(), [])

	def test_a_step_that_fails_does_not_stop_the_ones_after_it(self):
		def boom():
			raise RuntimeError("no way")

		steps = self.steps(("first", ok(self.order, "first")), ("second", boom), ("third", ok(self.order, "third")))
		failed = install.run_steps(steps)
		self.assertEqual(self.order, ["first", "third"])
		self.assertEqual(failed, [("second", "no way")])

	def test_the_whole_error_is_in_the_error_log(self):
		def boom():
			raise RuntimeError("no way")

		install.run_steps(self.steps(("the second step", boom)))
		logs = self.logs()
		self.assertEqual(len(logs), 1)
		self.assertIn("the second step", logs[0].error)
		self.assertIn("Traceback", logs[0].error)
		self.assertIn("no way", logs[0].error)

	def test_each_failed_step_is_logged_on_its_own(self):
		def boom():
			raise RuntimeError("x")

		install.run_steps(self.steps(("one", boom), ("two", ok(self.order, "two")), ("three", boom)))
		self.assertEqual(len(self.logs()), 2)

	def test_the_installation_fails_and_names_the_steps(self):
		def boom():
			raise RuntimeError("no way")

		steps = self.steps(("the permissions", boom), ("fine", ok(self.order, "fine")))
		with self.assertRaises(frappe.ValidationError) as caught:
			from unittest import mock

			with mock.patch.object(install, "STEPS", steps):
				install.after_install()
		self.assertIn("the permissions", str(caught.exception))
		self.assertEqual(self.order, ["fine"])

	def test_the_installation_succeeds_when_all_steps_work(self):
		from unittest import mock

		steps = self.steps(("a", ok(self.order, "a")))
		with mock.patch.object(install, "STEPS", steps):
			install.after_install()
		self.assertEqual(self.order, ["a"])

	def test_every_real_step_names_a_function_that_exists(self):
		for label, path in install.STEPS:
			self.assertTrue(callable(install._function(path)), f"{label}: {path}")


class _Registry:
	"""Where the test steps live, so that the runner can find them by 'module:function'."""
