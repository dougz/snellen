import unittest

import game

class PuzzleTest(unittest.TestCase):
  def test_canonical(self):
    def check(before, after):
      self.assertEqual(game.Puzzle.canonicalize_answer(before), after)

    check("foo", "FOO")

    check("123", "")

    check("car 54", "CAR")

    check("Al Kaline stuck in Ph one booth",
          "ALKALINESTUCKINPHONEBOOTH")

    check("Montréal, über, 12.89, Mère, Françoise, noël, 889",
          "MONTREALUBERMEREFRANCOISENOEL")

    check("✈✈✈ Galactic Trendsetters ✈✈✈",
          "GALACTICTRENDSETTERS")

if __name__ == "__main__":
  unittest.main()


